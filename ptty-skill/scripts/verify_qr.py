#!/usr/bin/env python3
"""Verify a downloaded, decorated event QR without altering or regenerating it."""
import argparse
import hashlib
import json
from pathlib import Path

from qr_export import validate_event_url


def verify(image_path, url_file):
    from PIL import Image
    import zxingcpp

    image_path, url_file = Path(image_path), Path(url_file)
    payload = validate_event_url(url_file.read_text(encoding='utf-8').strip())
    raw = image_path.read_bytes()
    with Image.open(image_path) as image:
        if image.format not in {'PNG', 'JPEG'} or getattr(image, 'n_frames', 1) != 1:
            raise ValueError('verify the downloaded static PNG/JPEG; render vector outputs separately')
        image.load()
        size = list(image.size)
        results = zxingcpp.read_barcodes(image)
    if len(results) != 1 or results[0].format != zxingcpp.BarcodeFormat.QRCode or results[0].text != payload:
        raise ValueError('expected exactly one QR with the unchanged platform URL')
    return {'verification': 'decoded_payload_equal', 'image_size': size,
            'output_sha256': hashlib.sha256(raw).hexdigest(),
            'payload_sha256': hashlib.sha256(payload.encode()).hexdigest(),
            'image_modified': False, 'mobile_scan_verified': False,
            'artwork_review_required': ['logo', 'footer', 'contrast', 'quiet_zone']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--url-file', required=True)
    parser.add_argument('--out', required=True, help='new JSON verification receipt')
    args = parser.parse_args()
    try:
        result = verify(args.image, args.url_file)
        with Path(args.out).open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    except (OSError, ValueError, ImportError):
        parser.exit(2, 'QR verification failed; inspect file, payload and dependencies. No image modified.\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
