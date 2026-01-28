import argparse
import os
import subprocess


def run(args: list[str], input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, input=input_bytes, text=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres_dump", required=True)
    parser.add_argument("--neo4j_dump", required=True)
    parser.add_argument("--postgres_container", default="affinity-postgres")
    parser.add_argument("--postgres_db", default="affinity")
    parser.add_argument("--postgres_user", default="affinity")
    parser.add_argument("--neo4j_container", default="affinity-neo4j")
    parser.add_argument("--neo4j_db", default="neo4j")
    args = parser.parse_args()

    pg_dump_path = os.path.abspath(args.postgres_dump)
    with open(pg_dump_path, "rb") as f:
        content = f.read()
    run(["docker", "exec", "-i", args.postgres_container, "psql", "-U", args.postgres_user, args.postgres_db], input_bytes=content)

    neo_dump_path = os.path.abspath(args.neo4j_dump)
    neo_tmp = "/tmp/neo4j_restore.dump"
    run(["docker", "cp", neo_dump_path, f"{args.neo4j_container}:{neo_tmp}"])
    run(
        [
            "docker",
            "exec",
            args.neo4j_container,
            "neo4j-admin",
            "load",
            f"--from={neo_tmp}",
            "--database",
            args.neo4j_db,
            "--force",
        ]
    )
    run(["docker", "exec", args.neo4j_container, "rm", "-f", neo_tmp])


if __name__ == "__main__":
    main()

