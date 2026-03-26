def replace_in_file(args):
    source_string = bytes(args.source_string)
    replacement_string = bytes(args.replacement_string)

    for file_name in args.files:
        with open(file_name, "rb") as f:
            data = f.read()

        data = data.replace(source_string, replacement_string)

        with open(file_name, "wb") as f:
            f.write(data)
