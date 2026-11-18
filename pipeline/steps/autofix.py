"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    error_issues = [i for i in issues if i.severity == ERROR]
    fixes = []
    removed_stems = set()

    # 1. DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE: xoá ảnh + nhãn
    for iss in error_issues:
        if iss.code.startswith("DUP_IMAGE") or iss.code in ("LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"):
            if iss.image in removed_stems:
                continue
            removed_stems.add(iss.image)
            img_p = ds.image_path(iss.image)
            if img_p and img_p.exists():
                img_p.unlink()
            for ext in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
                p = ds.images_dir / f"{iss.image}{ext}"
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass
            lab_p = ds.label_path(iss.image)
            if lab_p and lab_p.exists():
                lab_p.unlink()
            fixes.append({
                "image": iss.image,
                "line": "",
                "action": "remove_image",
                "before": iss.code,
                "after": "(xoá ảnh + nhãn)",
            })

    # 2. BAD_CLASS_NAME: ghi lại names trong data.yaml đúng cfg["classes"]
    rename_done = False
    for iss in error_issues:
        if iss.code == "BAD_CLASS_NAME" and not rename_done:
            rename_done = True
            before_names = ds.yaml_names()
            data = {}
            if ds.yaml_path.exists():
                data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
            data["names"] = list(cfg["classes"])
            ds.yaml_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": str(before_names),
                "after": str(cfg["classes"]),
            })

    # 3. MISSING_LABEL_FILE: KHÔNG tạo file, chỉ ghi 1 dòng fix chuyển người gán
    needs_label_stems = set()
    for iss in error_issues:
        if iss.code == "MISSING_LABEL_FILE":
            if iss.image not in removed_stems and iss.image not in needs_label_stems:
                needs_label_stems.add(iss.image)
                fixes.append({
                    "image": iss.image,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })

    # 4. Lỗi dòng nhãn: BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX, BOX_OUT_OF_IMAGE
    LINE_DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    line_issues_by_img = defaultdict(lambda: defaultdict(list))
    for iss in error_issues:
        if iss.image in removed_stems or iss.image in ("<dataset>", "data.yaml"):
            continue
        if iss.code in LINE_DROP_CODES or iss.code == "BOX_OUT_OF_IMAGE":
            if iss.line is not None:
                line_issues_by_img[iss.image][iss.line].append(iss)

    for stem, lines_dict in line_issues_by_img.items():
        lab_p = ds.label_path(stem)
        if not lab_p.exists():
            continue
        raw_lines = lab_p.read_text(encoding="utf-8", errors="replace").splitlines()

        to_drop = set()
        to_clip = {}

        for line_no, iss_list in sorted(lines_dict.items()):
            if not (1 <= line_no <= len(raw_lines)):
                continue
            raw_line = raw_lines[line_no - 1]

            has_drop = any(i.code in LINE_DROP_CODES for i in iss_list)
            if has_drop:
                to_drop.add(line_no)
                fixes.append({
                    "image": stem,
                    "line": line_no,
                    "action": "drop_line",
                    "before": raw_line,
                    "after": "(xoá dòng)",
                })
            else:
                try:
                    cls_id, cx, cy, w, h = parse_yolo_line(raw_line)
                    x1 = cx - w / 2.0
                    x2 = cx + w / 2.0
                    y1 = cy - h / 2.0
                    y2 = cy + h / 2.0

                    x1_c = max(0.0, min(1.0, x1))
                    x2_c = max(0.0, min(1.0, x2))
                    y1_c = max(0.0, min(1.0, y1))
                    y2_c = max(0.0, min(1.0, y2))

                    new_w = x2_c - x1_c
                    new_h = y2_c - y1_c
                    if new_w <= 0.0 or new_h <= 0.0:
                        to_drop.add(line_no)
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "drop_line",
                            "before": raw_line,
                            "after": "(xoá dòng: box ngoài ảnh)",
                        })
                    else:
                        new_cx = (x1_c + x2_c) / 2.0
                        new_cy = (y1_c + y2_c) / 2.0
                        clipped_str = f"{cls_id} {new_cx:.6f} {new_cy:.6f} {new_w:.6f} {new_h:.6f}"
                        to_clip[line_no] = clipped_str
                        fixes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "clip_box",
                            "before": raw_line,
                            "after": clipped_str,
                        })
                except ValueError:
                    to_drop.add(line_no)
                    fixes.append({
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": raw_line,
                        "after": "(xoá dòng: không parse được)",
                    })

        new_lines = []
        for idx, r_line in enumerate(raw_lines):
            l_no = idx + 1
            if l_no in to_drop:
                continue
            elif l_no in to_clip:
                new_lines.append(to_clip[l_no])
            else:
                new_lines.append(r_line)

        new_content = "\n".join(new_lines)
        if new_lines:
            new_content += "\n"
        lab_p.write_text(new_content, encoding="utf-8")

    return fixes
