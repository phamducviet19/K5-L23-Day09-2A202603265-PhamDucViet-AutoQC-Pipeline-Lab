"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    if preds is None:
        preds = {}

    cfg_so = cfg.get("second_opinion", {})
    conf_thr = cfg_so.get("conf", 0.25)
    min_area_px = cfg_so.get("min_area_px", 600)
    fp_conf = cfg_so.get("fp_conf", 0.1)
    iou_missing = cfg_so.get("iou_missing", 0.3)
    iou_match = cfg_so.get("iou_match", 0.5)
    iou_loose = cfg_so.get("iou_loose", 0.5)

    issues = []

    for img_p in ds.image_files():
        stem = img_p.stem
        if stem not in preds:
            continue
        if not ds.label_path(stem).exists():
            continue

        im_size = ds.image_size(stem)
        W, H = im_size if im_size is not None else (640, 480)

        all_preds = preds.get(stem, [])
        # P = dự đoán có conf >= conf VÀ diện tích px >= min_area_px
        P = [r for r in all_preds if r[1] >= conf_thr and (r[4] * W * r[5] * H) >= min_area_px]

        # Đọc nhãn hợp lệ, lưu cả số dòng gốc
        raw_lines = ds.read_label_lines(stem)
        valid_label_lines = []
        if raw_lines:
            for line_no, ln in raw_lines:
                try:
                    b = parse_yolo_line(ln)
                except ValueError:
                    continue
                if 0 <= b[0] < len(ds.classes):
                    valid_label_lines.append((line_no, b))

        L = [b for _, b in valid_label_lines]

        # Kiểm tra từng dự đoán trong P
        for r in P:
            pred_cls = int(r[0])
            pred_conf = float(r[1])
            pred_box = (r[2], r[3], r[4], r[5])
            cls_name = ds.classes[pred_cls] if 0 <= pred_cls < len(ds.classes) else f"lớp {pred_cls}"

            cands_same = []
            cands_diff = []
            for l in L:
                lbl_cls = l[0]
                lbl_box = (l[1], l[2], l[3], l[4])
                iou = iou_xywh(pred_box, lbl_box)
                if iou >= iou_missing:
                    if lbl_cls == pred_cls:
                        cands_same.append((l, iou))
                    else:
                        cands_diff.append((l, iou))

            cands = cands_same + cands_diff

            if not cands:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING", stem,
                                    f"model phát hiện {cls_name} (conf {pred_conf:.2f}) nhưng nhãn thiếu",
                                    line=None, extra={"conf": pred_conf}))
            elif cands_same:
                best_iou_same = max(iou for _, iou in cands_same)
                if best_iou_same < iou_loose:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"box nhãn lỏng/lệch (IoU {best_iou_same:.2f} < {iou_loose})",
                                        line=None, extra={"conf": pred_conf, "iou": best_iou_same}))
            else:
                best_iou_diff = max(iou for _, iou in cands_diff)
                if best_iou_diff >= iou_match:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                                        f"gán nhầm lớp? model đoán {cls_name} (conf {pred_conf:.2f}), nhãn gán khác (IoU {best_iou_diff:.2f})",
                                        line=None, extra={"conf": pred_conf, "iou": best_iou_diff}))

        # Kiểm tra POSSIBLE_FALSE_POS cho từng dòng nhãn
        fp_preds = [r for r in all_preds if r[1] >= fp_conf]
        for line_no, (lbl_cls, cx, cy, w, h) in valid_label_lines:
            lbl_box = (cx, cy, w, h)
            matches_any = any(iou_xywh(lbl_box, (r[2], r[3], r[4], r[5])) >= iou_missing for r in fp_preds)
            if not matches_any:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"dòng {line_no}: box nhãn không khớp vật nào model thấy",
                                    line=line_no, extra={"line": line_no}))

    return issues
