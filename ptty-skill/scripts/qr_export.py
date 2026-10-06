#!/usr/bin/env python3
"""Create a verified QR graphic, or preserve a platform mini-program code."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_event_url(payload):
    url = urlsplit(payload)
    if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password:
        raise ValueError('a real http(s) event URL without embedded credentials is required')
    private_keys = {'uisstr', 'password', 'passwd', 'pwd', 'token', 'access_token', 'refresh_token',
                    'authorization', 'cookie', 'session', 'sessionid', 'api_key', 'apikey'}
    parts = [url.query, url.fragment.split('?', 1)[-1] if '?' in url.fragment else url.fragment]
    if any(key.casefold() in private_keys for part in parts for key, _ in parse_qsl(part)):
        raise ValueError('public QR must not contain temporary download signatures or login parameters')
    # Preserve the platform's exact scheme and route. A different HTTPS app
    # may be deployed on a hostname whose working public QR uses HTTP.
    return payload


def generate(args):
    import qrcode
    import zxingcpp
    from PIL import Image, ImageDraw, ImageFont

    output = Path(args.out)
    destinations = [output, Path(str(output) + ".verification.json")]
    if args.pdf:
        destinations.append(output.with_suffix(".pdf"))
    if output.suffix.lower() != ".png":
        raise ValueError("--out must end in .png")
    if any(p.exists() for p in destinations):
        raise ValueError("output exists; use a new filename")
    if args.module_pixels < 4:
        raise ValueError("module pixels must be at least 4")
    if args.miniapp and not args.source_image:
        raise ValueError("miniapp requires a downloaded source image")
    if args.miniapp and args.logo_position == "center":
        raise ValueError("mini-program code cannot be covered by a center logo")
    if args.source_image and args.logo_position == "center":
        raise ValueError("center logo requires a newly generated URL QR")
    payload = None
    if args.url or args.url_file:
        payload = args.url if args.url else Path(args.url_file).read_text(encoding="utf-8").strip()
        validate_event_url(payload)
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=args.module_pixels, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        code = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        source_hash = None
    else:
        raw = Path(args.source_image).read_bytes()
        code = Image.open(args.source_image).convert("RGB")
        source_hash = digest(raw)
        if not args.miniapp:
            if not args.expected_payload_file:
                raise ValueError("ordinary source QR requires --expected-payload-file")
            payload = Path(args.expected_payload_file).read_text(encoding="utf-8").strip()
            if payload.startswith(('http:', 'https:')):
                validate_event_url(payload)

    logo = Image.open(args.logo).convert("RGBA") if args.logo else None
    if logo and args.logo_position == "center":
        edge = max(8, int(code.width * 0.15))
        logo.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        pad = max(2, args.module_pixels // 2)
        panel = Image.new("RGB", (logo.width + 2 * pad, logo.height + 2 * pad), "white")
        panel.paste(logo, (pad, pad), logo)
        code.paste(panel, ((code.width - panel.width) // 2, (code.height - panel.height) // 2))

    margin = max(24, args.module_pixels * 4)
    width = max(code.width + 2 * margin, 360)
    font_path = args.font
    if args.footer and any(ord(c) > 127 for c in args.footer) and not font_path:
        raise ValueError("non-ASCII footer requires --font with suitable glyphs")
    font = ImageFont.truetype(font_path, args.font_size) if font_path else ImageFont.load_default(size=args.font_size)
    draw = ImageDraw.Draw(Image.new("RGB", (width, 1)))
    lines = []
    for paragraph in args.footer.splitlines():
        line = ""
        for char in paragraph:
            if line and draw.textlength(line + char, font=font) > width - 2 * margin:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    line_height = args.font_size + 10
    header_logo = logo if logo and args.logo_position == "header" else None
    if header_logo:
        header_logo.thumbnail((width // 3, 120), Image.Resampling.LANCZOS)
    header_height = header_logo.height + margin if header_logo else 0
    footer_height = len(lines) * line_height + margin if lines else 0
    canvas = Image.new("RGB", (width, code.height + 2 * margin + header_height + footer_height), "white")
    if header_logo:
        canvas.paste(header_logo, ((width - header_logo.width) // 2, margin), header_logo)
    origin = ((width - code.width) // 2, margin + header_height)
    canvas.paste(code, origin)
    d = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        d.text((width / 2, origin[1] + code.height + margin + i * line_height), line, fill="black", font=font, anchor="mt")

    if args.miniapp:
        crop = canvas.crop((origin[0], origin[1], origin[0] + code.width, origin[1] + code.height))
        if crop.tobytes() != code.tobytes():
            raise ValueError("platform mini-program code pixels changed")
        verification = "platform_original_preserved"
    else:
        results = zxingcpp.read_barcodes(canvas)
        if not any(r.text == payload for r in results):
            raise ValueError("final QR failed exact payload decoding; reduce logo coverage")
        verification = "decoded_payload_equal"
    # No files are committed before validation succeeds.
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG")
    if args.pdf:
        canvas.save(output.with_suffix(".pdf"), format="PDF", resolution=150)
    report = {"verification": verification, "source_sha256": source_hash,
              "payload_sha256": digest(payload.encode()) if payload is not None else None,
              "output_sha256": digest(output.read_bytes()), "image_size": list(canvas.size),
              "code_size": list(code.size), "code_origin": list(origin),
              "logo_position": args.logo_position if logo else None,
              "mobile_scan_verified": False}
    Path(str(output) + ".verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--url-file")
    source.add_argument("--source-image")
    p.add_argument("--miniapp", action="store_true")
    p.add_argument("--expected-payload-file")
    p.add_argument("--out", required=True)
    p.add_argument("--logo")
    p.add_argument("--logo-position", choices=("header", "center"), default="header")
    p.add_argument("--footer", default="")
    p.add_argument("--font")
    p.add_argument("--font-size", type=int, default=24)
    p.add_argument("--module-pixels", type=int, default=10)
    p.add_argument("--pdf", action="store_true")
    return p


if __name__ == "__main__":
    cli = parser()
    try:
        print(json.dumps(generate(cli.parse_args()), ensure_ascii=False, indent=2))
    except (ValueError, OSError, ImportError) as exc:
        cli.exit(2, f"QR export failed: {exc}\n")
