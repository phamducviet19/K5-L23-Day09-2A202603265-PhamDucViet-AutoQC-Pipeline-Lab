"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    cfg_lf = cfg.get("label_format", {})
    overflow_tol = cfg_lf.get("overflow_tol", 0.002)
    dup_box_iou = cfg_lf.get("dup_box_iou", 0.9)
    min_box_px = cfg_lf.get("min_box_px", 12)
    max_box_frac = cfg_lf.get("max_box_frac", 0.95)

    issues = []
    for lf in ds.label_files():
        stem = lf.stem
        lines = ds.read_label_lines(stem)
        if not lines:
            continue

        im_size = ds.image_size(stem)
        seen_boxes = []  # list of (class_id, (cx, cy, w, h), line_no)

        for line_no, ln in lines:
            try:
                cls_id, cx, cy, w, h = parse_yolo_line(ln)
            except ValueError:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng {line_no} sai định dạng: {ln!r}", line=line_no))
                continue

            if not (0 <= cls_id < len(ds.classes)):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls_id} ngoài phạm vi 0..{len(ds.classes)-1}", line=line_no))
                continue

            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"box có w={w} hoặc h={h} <= 0", line=line_no))
                continue

            # Mép box
            x1 = cx - w / 2
            x2 = cx + w / 2
            y1 = cy - h / 2
            y2 = cy + h / 2
            overflow = max(0.0, -x1, -y1, x2 - 1.0, y2 - 1.0)
            if overflow > overflow_tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ra ngoài ảnh: overflow={overflow:.4f}", line=line_no, extra={"overflow": overflow}))

            # DUP_BOX: cùng lớp với dòng trước đó và IoU > dup_box_iou
            for prev_cls, prev_box, prev_line in seen_boxes:
                if prev_cls == cls_id and iou_xywh((cx, cy, w, h), prev_box) > dup_box_iou:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, f"trùng lặp box với dòng {prev_line}", line=line_no))
                    break
            seen_boxes.append((cls_id, (cx, cy, w, h), line_no))

            # BOX_TINY
            if im_size is not None:
                W, H = im_size
                short_side = min(w * W, h * H)
                if short_side < min_box_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem, f"cạnh ngắn {short_side:.1f}px < {min_box_px}px", line=line_no))

            # BOX_HUGE
            if (w * h) > max_box_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, f"diện tích {w * h:.3f} > {max_box_frac}", line=line_no))

    return issues
