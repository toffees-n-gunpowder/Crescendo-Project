"""
Perceptual image hashing (dHash) for spotting reused cover art.

An MD5 of the image bytes only finds byte-identical files, which is useless
here: Jamendo re-encodes the same uploaded picture per album ID, so twenty
albums can display an identical banner while every file differs. A perceptual
hash describes what the image *looks like*, so re-encoding, resizing and
recompression all collapse to the same (or a very near) value.

dHash works by shrinking the image to 9x8 greyscale and recording, for each of
the 8 rows, whether each pixel is brighter than the one to its right. That is
64 comparisons - one 64-bit fingerprint. Two images are "the same picture" when
their fingerprints differ in only a few bits.
"""

import io

from PIL import Image

HASH_SIZE = 8


def dhash(image_bytes):
    """Return a 64-bit perceptual fingerprint, or None if the data isn't an image."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        # Convert first: some Jamendo covers are palettised or have alpha.
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
    """Hamming distance: how many of the 64 bits differ."""
    return bin(hash_a ^ hash_b).count('1')


def cluster(items, max_distance):
    """
    Group (key, hash) pairs into buckets of visually-identical images.

    Union-find over pairwise Hamming distance. The catalogue is small enough
    that the O(n^2) comparison is irrelevant, and it avoids the false splits a
    naive "first match wins" pass produces.
    """
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
