import argparse
import os
import subprocess
from datetime import datetime


def run(args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, text=True, capture_output=capture)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", default="backups")
    parser.add_argument("--timestamp", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--postgres_container", default="affinity-postgres")
    parser.add_argument("--postgres_db", default="affinity")
    parser.add_argument("--postgres_user", default="affinity")
    parser.add_argument("--neo4j_container", default="affinity-neo4j")
    parser.add_argument("--neo4j_db", default="neo4j")
    args = parser.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    pg_path = os.path.join(out_dir, f"postgres_{args.timestamp}.sql")
    pg_dump = run(
        ["docker", "exec", args.postgres_container, "pg_dump", "-U", args.postgres_user, args.postgres_db],
        capture=True,
    )
    with open(pg_path, "w", encoding="utf-8") as f:
        f.write(pg_dump.stdout)

    neo_tmp = f"/tmp/neo4j_{args.timestamp}.dump"
    neo_out = os.path.join(out_dir, f"neo4j_{args.timestamp}.dump")
    run(
        [
            "docker",
            "exec",
            args.neo4j_container,
            "neo4j-admin",
            "dump",
            "--database",
            args.neo4j_db,
            f"--to={neo_tmp}",
            "--overwrite-destination",
        ]
    )
    run(["docker", "cp", f"{args.neo4j_container}:{neo_tmp}", neo_out])
    run(["docker", "exec", args.neo4j_container, "rm", "-f", neo_tmp])

    print(pg_path)
    print(neo_out)


if __name__ == "__main__":
    main()

