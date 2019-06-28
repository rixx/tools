from datetime import datetime, timedelta
import random
import requests
import sys
import time

START_DATE = datetime.now()
TOTAL = 3241
DAYS = 5
DAILY = TOTAL / DAYS
BUCKETS = [
    {
        8: int(DAILY * 0.05 + random.randint(-10, 10)),
        9: int(DAILY * 0.06 + random.randint(-10, 10)),
        10: int(DAILY * 0.08 + random.randint(-20, 20)),
        11: int(DAILY * 0.1 + random.randint(-20, 20)),
        12: int(DAILY * 0.05 + random.randint(-10, 10)),
        13: int(DAILY * 0.05 + random.randint(-10, 10)),
        14: int(DAILY * 0.15 + random.randint(-20, 20)),
        15: int(DAILY * 0.13 + random.randint(-20, 20)),
        16: int(DAILY * 0.12 + random.randint(-20, 20)),
        17: int(DAILY * 0.09 + random.randint(-20, 20)),
        18: int(DAILY * 0.07 + random.randint(-10, 10)),
        19: int(DAILY * 0.05 + random.randint(-10, 10)),
    }
    for _ in range(DAYS)
]
BASE_PATH = []
PATHS = [
    [
        "https://www.deutsche-bank-bauspar.de/content/kundenmagazin.html",
        "https://www.deutsche-bank-bauspar.de/data/docs/Magazin_PlanB_Ausgabe_1-2019.pdf",
    ]
]
USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64; rv:65.0) Gecko/20100101 Firefox/65.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36 Edge/16.16299",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36 Edge/16.16299",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36 Edge/16.16299",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36 Edge/16.16299",
    "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:50.0) Gecko/20100101 Firefox/50.0",
    "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:50.0) Gecko/20100101 Firefox/50.0",
    "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)",
    "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)",
    "Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/603.3.8 (KHTML, like Gecko)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36",
]


def click():
    path = random.choice(PATHS)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "User-Agent": random.choice(USER_AGENTS),
    }
    last_url = None
    for subpath in path:
        if last_url:
            headers["Referer"] = last_url
            requests.get(subpath, headers=headers)
            last_url = subpath


def clickity():
    try:
        total_downloaded = 0
        current_day = abs((datetime.now() - START_DATE).days)
        bucket = old_bucket = None
        while total_downloaded < TOTAL:
            if current_day > len(BUCKETS):
                print("Time is over! Downloaded {}".format(total_downloaded))
                sys.exit()
            _now = datetime.now()
            current_day = abs((_now - START_DATE).days)
            old_bucket = bucket
            bucket = _now.hour
            if old_bucket != bucket:
                old_day = current_day if old_bucket != 0 else max(current_day - 1, 0)
                if old_bucket in BUCKETS[old_day] and BUCKETS[old_day][old_bucket] > 0:
                    print(
                        "Closing bucket {} of day {} ({} remaining)".format(
                            old_bucket, old_day + 1, BUCKETS[old_day][old_bucket]
                        )
                    )
                    for _ in range(BUCKETS[old_day][old_bucket]):
                        click()
                        total_downloaded += 1
                        BUCKETS[old_day][old_bucket] -= 1
                print(
                    "Starting bucket {} of day {} ({} remaining.)".format(
                        bucket, current_day + 1, BUCKETS[current_day][bucket]
                    )
                )
            if bucket in BUCKETS[current_day] and BUCKETS[current_day][bucket] > 0:
                click()
                total_downloaded += 1
                BUCKETS[current_day][bucket] -= 1
                time.sleep(random.randint(0, 60))
            elif bucket in BUCKETS[current_day]:
                print("Finished bucket {} of day {}".format(bucket, current_day + 1))
                sl = (
                    (_now + timedelta(hours=1)).replace(minute=0, second=0) - _now
                ).seconds
                time.sleep(sl)
                print("Sleeping {} minutes until next bucket.".format(sl))
            else:
                print("Sleeping until next bucket.")
        print("Finished! Downloaded {}".format(total_downloaded))
        sys.exit()
    except KeyboardInterrupt:
        print("Downloaded {}".format(total_downloaded))
        sys.exit()


if __name__ == "__main__":
    clickity()
