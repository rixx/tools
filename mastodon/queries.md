# Queries you might need on your Mastodon server

## Don't allow unlimited invites

```sql
UPDATE
  invites
SET
  expires_at = '2021-03-25 0:00'
WHERE
  (max_uses is null AND expires_at is null)
  OR (uses < max_uses AND max_uses > 10 AND expires_at is null)
  OR (uses < max_uses AND max_uses > 10 AND now() < expires_at)
  OR (max_uses is null AND now() < expires_at);
```

## How many users have joined recently?

```sql
SELECT
  created_at::date AS "date",
  count("created_at") AS "registrations"
FROM
  users
WHERE
  users.created_at BETWEEN NOW() - INTERVAL '14 DAYS'
  and NOW()
GROUP BY
  date
ORDER BY
  date;
```

## Show local users with the most followers

```sql
SELECT
  accounts.username,
  accounts.created_at,
  count(follows.id)
FROM
  accounts
  JOIN follows on accounts.id = follows.target_account_id
WHERE
  accounts.domain IS NULL
GROUP BY
  accounts.username,
  accounts.created_at
ORDER BY
  count DESC
LIMIT
  100;
```

## Who invited a lot of users recently?

We use this mostly to make sure that nobody is spamming invites somewhere – we already limit the reach of invites (see
above), but we also want to be able to figure out fast when somebody is creating a huge load by inviting dozens or
hundreds of users.

```sql
SELECT
  a2.username,
  count(a1.username)
FROM
  users AS u1
  JOIN accounts AS a1 ON a1.id = u1.account_id
  JOIN invites ON u1.invite_id = invites.id
  JOIN users AS u2 ON invites.user_id = u2.id
  JOIN accounts AS a2 ON a2.id = u2.account_id
WHERE
  u1.created_at BETWEEN NOW() - INTERVAL '7 days'
  AND NOW()
GROUP BY
  a2.username
ORDER BY
  count(a1.username) desc;
```

## Show invites by a specific user

```sql
SELECT
  invites.code,
  invites.created_at,
  invites.expires_at,
  invites.max_uses,
  invites.uses
FROM
  invites
  JOIN users AS u1 ON invites.user_id = u1.id
  JOIN accounts ON u1.account_id = accounts.id
WHERE
  accounts.username LIKE 'insert username here';
```

## Show users invited by a specific user

Please note that we use this as a moderation tool and only when needed: When a troll joins the instance and we kick
them, we need to know if the user inviting them has issued similar invites to other accounts, or if it was a one-off
mistake. We don't regularly track invites otherwise (ain't nobody got time).

```
SELECT
  a1.username,
  u1.created_at
FROM
  accounts AS a1
  JOIN users AS u1 ON u1.account_id = a1.id
  JOIN invites ON u1.invite_id = invites.id
  JOIN users AS u2 ON invites.user_id = u2.id
  JOIN accounts AS a2 ON u2.account_id = a2.id
WHERE
  a2.username LIKE 'insert username here';
```

## Show OAuth applications by name

Note: crossposter, bridge, feed2toot, wordpress

```sql
SELECT id, name FROM oauth_applications WHERE LOWER(name) LIKE '%Bridge%';
```

## Show public posts by OAuth application

```sql
SELECT
  statuses.uri,
  statuses.application_id
FROM
  statuses
WHERE
  statuses.application_id IN (
    SELECT
      id
    FROM
      oauth_applications
    WHERE
      LOWER(name) LIKE '%crossposter%'
      or LOWER(name) LIKE '%wordpress%'
      or LOWER(name) LIKE '%feed2toot%'
      or LOWER(name) LIKE '%bridge%'
      or LOWER(name) LIKE '%share%'
  )
  AND statuses.reblog_of_id IS null
  AND statuses.in_reply_to_id IS null
  AND statuses.visibility <= 1
ORDER BY
  statuses.id DESC
LIMIT
  10;
```
