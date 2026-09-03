import io

from PIL import Image

HASH_SIZE = 8


def dhash(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert('L').resize((HASH_SIZE + 1, HASH_SIZE), Image.LANCZOS)
    except Exception:
        return None

    pixels = list(image.getdata())
    bits = 0
    position = 0
    for row in range(HASH_SIZE):
        offset = row * (HASH_SIZE + 1)
        for col in range(HASH_SIZE):
            left = pixels[offset + col]
            right = pixels[offset + col + 1]
            if left > right:
                bits |= 1 << position
            position += 1
    return bits


def distance(hash_a, hash_b):
    return bin(hash_a ^ hash_b).count('1')


def cluster(items, max_distance):
    parent = {key: key for key, _ in items}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(a, b):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for i in range(len(items)):
        key_a, hash_a = items[i]
        for j in range(i + 1, len(items)):
            key_b, hash_b = items[j]
            if distance(hash_a, hash_b) <= max_distance:
                union(key_a, key_b)

    groups = {}
    for key, _ in items:
        groups.setdefault(find(key), []).append(key)
    return list(groups.values())
