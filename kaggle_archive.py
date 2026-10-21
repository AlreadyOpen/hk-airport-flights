"""The archive: every complete Hong Kong day of live/changes-YYYY-MM-DD.parquet as its own public Kaggle dataset,
helenkwok/hk-airport-flights-YYYY-MM-DD, created once and never versioned or deleted (Kaggle public storage is free; the
precedent is AlreadyOpen/world-flights' one dataset per day). A day leaves the bucket only when it is older than HF_DAYS and
`kaggle datasets files` lists it. Also refreshes the Hugging Face dataset card (hf/README.md). Runs daily in archive.yml.
Needs HF_TOKEN and KAGGLE_API_TOKEN. Usage: python3 kaggle_archive.py      (self-test, no network: python3 kaggle_archive.py test)"""
import datetime, json, os, re, subprocess, sys, tempfile, time
import kaggle_mirror

REPO = 'milleleaf/hk-airport-flights'
HF_DAYS = 7
DAY = re.compile(r'live/changes-(\d{4}-\d{2}-\d{2})\.parquet')
HKT = datetime.timezone(datetime.timedelta(hours=8))
slug = lambda day: f'helenkwok/hk-airport-flights-{day}'


def plan(paths, today):
    """(days to archive, days to drop from the bucket once archived): complete days before today; drop those older than HF_DAYS"""
    days = sorted(m[1] for p in paths if (m := DAY.fullmatch(p)) and m[1] < today)
    cut = str(datetime.date.fromisoformat(today) - datetime.timedelta(days=HF_DAYS))
    return days, [d for d in days if d < cut]


def listed(s, day):
    r = subprocess.run(['kaggle', 'datasets', 'files', s, '-v', '--page-size', '200'], capture_output=True, text=True)
    return r.returncode == 0 and f'changes-{day}.parquet' in r.stdout


def main():
    from huggingface_hub import HfApi, batch_bucket_files, download_bucket_files, list_bucket_tree
    here = os.path.dirname(os.path.abspath(__file__))
    api = HfApi(); api.create_repo(REPO, repo_type='dataset', exist_ok=True)
    api.upload_file(path_or_fileobj=os.path.join(here, 'hf', 'README.md'), path_in_repo='README.md', repo_id=REPO, repo_type='dataset',
                    commit_message='card')
    days, drop = plan([f.path for f in list_bucket_tree(REPO, prefix='live', recursive=True)], str(datetime.datetime.now(HKT).date()))
    done, gone = [], []
    for day in days:
        s, p = slug(day), f'live/changes-{day}.parquet'
        if not listed(s, day):
            if subprocess.run(['kaggle', 'datasets', 'files', s], capture_output=True).returncode == 0:
                print(f'::warning::{s} exists but does not list {p}: kept on the bucket, check by hand'); continue
            with tempfile.TemporaryDirectory() as root:
                download_bucket_files(REPO, [(p, os.path.join(root, p))])
                kaggle_mirror.mirror(s, f'AlreadyOpen: HK airport flights {day}', root, [p])
            for _ in range(30):                                        # Kaggle processes an upload before listing its files
                if listed(s, day): break
                time.sleep(60)
            else:
                print(f'::warning::{s}: not listed after 30 minutes; kept on the bucket'); continue
            done.append(f'https://www.kaggle.com/datasets/{s}')
        if day in drop: gone.append(p)
    if gone: batch_bucket_files(REPO, delete=gone)
    print(json.dumps({'archived': done, 'removed_from_bucket': gone}))


if __name__ == '__main__':
    if sys.argv[1:] == ['test']:
        p = ['live/flights.json'] + [f'live/changes-2026-10-{d:02d}.parquet' for d in range(1, 16)]
        days, drop = plan(p, '2026-10-15')
        assert days == [f'2026-10-{d:02d}' for d in range(1, 15)] and drop == [f'2026-10-{d:02d}' for d in range(1, 8)], (days, drop)
        assert 6 <= len('AlreadyOpen: HK airport flights 2026-10-15') <= 50
        print('kaggle_archive: self-test ok')
    else:
        main()
