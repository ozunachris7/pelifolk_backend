"""Never return credential material, including nested historical payloads."""
import re


def redact(value):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            normalized = re.sub(r'[^a-z0-9]', '', key.lower())
            if normalized != 'passwordchanged' and any(
                    word in normalized for word in ('password', 'secret', 'token', 'credential', 'apikey')):
                continue
            result[key] = redact(child)
        return result
    if isinstance(value, list):
        return [redact(child) for child in value]
    return value


def changed_fields(before, after):
    missing = object()
    changes = []

    def compare(old, new, path):
        if old is missing and new is missing:
            return
        if isinstance(old, dict) or isinstance(new, dict):
            if (old is missing or isinstance(old, dict)) and (new is missing or isinstance(new, dict)):
                old_dict = {} if old is missing else old
                new_dict = {} if new is missing else new
                for key in sorted(old_dict.keys() | new_dict.keys()):
                    compare(old_dict.get(key, missing), new_dict.get(key, missing), path + [key])
                if old_dict or new_dict:
                    return
        if old is not missing and new is not missing and old == new:
            return
        changes.append(dict(field='.'.join(path), before_present=old is not missing,
                            after_present=new is not missing,
                            before=None if old is missing else old, after=None if new is missing else new))

    compare(before if before is not None else missing, after if after is not None else missing, [])
    return changes
