import sys


DEFAULT_SIGN_TIMEOUT = 60


def main(client, parser):
    parser.add_argument(
        '--sign-timeout',
        help=f'Signing timeout in seconds ({DEFAULT_SIGN_TIMEOUT})',
        type=int,
        default=DEFAULT_SIGN_TIMEOUT)

    args = parser.parse_args()
    client.load_arguments(args)

    if client.request_timeout <= args.sign_timeout:
        print(
            f'ERROR: Sign timeout ({args.sign_timeout}) must be less than '
            + f'request timeout ({client.request_timeout})',
            file=sys.stderr)
        return
