# Queries you might need on your Mastodon server

## Don't save IPs

```sql
UPDATE users
SET current_sign_in_ip=null, last_sign_in_ip=null;

UPDATE session_activations
SET ip=null;
```

## Don't allow unlimited invites

```sql
UPDATE invites
SET expires_at='2021-03-25 0:00'
WHERE
    (max_uses is null and expires_at is null)
    OR (uses < max_uses and max_uses > 10 and expires_at is null)
    OR (uses < max_uses and max_uses > 10 and now() < expires_at)
    OR (max_uses is null and now() < expires_at);
```

## Who invited a lot of users recently?

```sql
SELECT a2.username, count(a1.username)
FROM
    users AS u1
    JOIN accounts AS a1 ON a1.id = u1.account_id
    JOIN invites ON u1.invite_id = invites.id
    JOIN users AS u2 ON invites.user_id = u2.id
    JOIN accounts AS a2 ON a2.id = u2.account_id
WHERE u1.created_at BETWEEN NOW() - INTERVAL '24 HOURS' AND NOW()
GROUP BY a2.username
ORDER BY count(a1.username) desc;
```
