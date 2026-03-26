from pathlib import Path


def _get_repo_url(args):
    return args.subrepo_url


def _exit(message, parser):
    raise ValueError(message)


def main(args, parser, nx_submodule_lib):
    if args.action == "create":
        if args.subrepo_dir.is_absolute():
            _exit('"--subrepo-dir" parameter must not be an absolute path', parser)

        if (repo_url := _get_repo_url(args)) is None:
            _exit(
                'One of "--subrepo-working-dir" or "--subrepo-url" must be set when creating Nx submodule',
                parser)

        nx_submodule_lib.create_submodule(
            dir=args.submodule_local_dir.resolve(),
            repo_url=repo_url,
            repo_dir=args.subrepo_dir,
            git_ref=args.git_ref)

    else:
        if args.submodule_local_dir:
            nx_submodule_lib.update_submodule(
                dir=args.submodule_local_dir.resolve(),
                git_ref=args.git_ref,
                fetch_url=args.fetch_url)
        else:
            repo_url = _get_repo_url(args)
            main_repo_dir = (args.main_repo_dir or Path.cwd()).resolve()
            nx_submodule_lib.find_and_update_submodules(
                main_repo_dir=main_repo_dir,
                git_ref=args.git_ref,
                repo_url=repo_url,
                fetch_url=args.fetch_url)
