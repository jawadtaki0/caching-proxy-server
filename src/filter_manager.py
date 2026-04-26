import os


def load_filter_list(file_path):
    if not os.path.exists(file_path):
        return set()

    entries = set()

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            entry = line.strip().lower()

            if entry:
                entries.add(entry)

    return entries


def is_host_allowed(host):
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    blacklist_path = os.path.join(data_dir, "blacklist.txt")
    whitelist_path = os.path.join(data_dir, "whitelist.txt")

    blacklist = load_filter_list(blacklist_path)
    whitelist = load_filter_list(whitelist_path)

    host = host.lower()

    if whitelist and host not in whitelist:
        return False

    if blacklist and host in blacklist:
        return False

    return True
