import json


def main(parser):
    args = parser.parse_args()

    input = json.load(args.source)
    systemData = input['desktop']['systemData']
    json.dump(systemData, args.destination)
