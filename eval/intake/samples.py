"""Bộ PDF mẫu ADC-001 (T-022) — dữ liệu GIẢ LẬP, không có thông tin khách thật.

Mỗi mẫu: các trang HTML + đáp án chuẩn hóa (đơn vị cm/kg/kGy, giờ Việt Nam "YYYY-MM-DDTHH:MM", None = không có
trong nguồn). Bản scan dựng lại từ bản văn bản số với chất lượng ảnh giảm dần. Ngày nhận chung: 01/10/2026 08:00.
"""

RECEIVED_AT = "2026-10-01T08:00:00+07:00"

CSS = """
body { font-family: Arial, sans-serif; font-size: 14px; margin: 36px 48px; color: #111; }
h2 { font-size: 18px; margin: 0 0 8px; }
table { border-collapse: collapse; margin-top: 12px; }
td { border: 1px solid #333; padding: 5px 10px; }
.meta { color: #333; font-size: 13px; }
"""


def page(body: str) -> str:
    return f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>'


def form(title: str, customer: str, number: str, rows: list[tuple[str, str]], note: str = "") -> str:
    cells = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    extra = f"<p>Ghi chú: {note}</p>" if note else ""
    return page(
        f"<h2>{title}</h2><p class='meta'>Khách hàng: {customer} (dữ liệu giả lập) · Số: {number} · "
        f"Ngày: 01/10/2026</p><table>{cells}</table>{extra}<p class='meta'>Người liên hệ: [Tên người liên hệ]</p>"
    )


def email(subject: str, text: str) -> str:
    return page(
        f"<p class='meta'>Từ: [email khách hàng] · Đến: kinhdoanh@[tên miền ADC] · Ngày: 01/10/2026 07:45<br>"
        f"Chủ đề: {subject}</p><p>{text}</p><p>Thanks,<br>[Tên người gửi]</p><p class='meta'>(dữ liệu giả lập)</p>"
    )


def ticket(
    page_from: int,
    page_to: int,
    product_name: str | None,
    quantity: int | None,
    dims: tuple[float, float, float] | None,
    weight: float | None,
    dose: float | None,
    priority: str | None,
    arrival: str | None,
    ret: str | None,
) -> dict:
    return {
        "page_from": page_from,
        "page_to": page_to,
        "fields": {
            "product_name": product_name,
            "quantity": quantity,
            "package_dimensions_cm": list(dims) if dims else None,
            "pkg_weight_kg": weight,
            "required_dose_kgy": dose,
            "priority": priority,
            "expected_arrival": arrival,
            "requested_return": ret,
        },
    }


TEXT_SAMPLES: list[dict] = [
    {
        "id": "01_phieu_giavi",
        "about": "Phiếu yêu cầu đủ 8 trường (TC1, TC11)",
        "pages": [
            form(
                "PHIẾU YÊU CẦU DỊCH VỤ CHIẾU XẠ",
                "Công ty TNHH Gia Vị Minh An",
                "YC-2026-1001-01",
                [
                    ("Tên sản phẩm", "Bột ớt xay khô"),
                    ("Số lượng", "120 thùng"),
                    ("Quy cách thùng", "40 x 30 x 25 cm, 8 kg/thùng"),
                    ("Liều chiếu yêu cầu", "10 kGy"),
                    ("Mức ưu tiên", "Thường"),
                    ("Giờ hàng đến", "09:00 ngày 02/10/2026"),
                    ("Giờ trả mong muốn", "16:00 ngày 02/10/2026"),
                ],
            )
        ],
        "tickets": [
            ticket(1, 1, "Bột ớt xay khô", 120, (40, 30, 25), 8, 10, "NORMAL", "2026-10-02T09:00", "2026-10-02T16:00")
        ],
    },
    {
        "id": "02_phieu_haisan_vip",
        "about": "Phiếu đủ trường, ưu tiên VIP ghi rõ",
        "pages": [
            form(
                "PHIẾU YÊU CẦU DỊCH VỤ CHIẾU XẠ",
                "Công ty CP Thủy Sản Biển Xanh",
                "YC-2026-1001-02",
                [
                    ("Sản phẩm", "Tôm sú đông lạnh"),
                    ("Số lượng", "60 thùng carton"),
                    ("Kích thước thùng", "50 x 40 x 20 cm"),
                    ("Khối lượng", "12 kg/thùng"),
                    ("Liều", "5 kGy"),
                    ("Ưu tiên", "VIP"),
                    ("Giao hàng tới kho", "07:30 03/10/2026"),
                    ("Nhận lại hàng", "15:00 03/10/2026"),
                ],
            )
        ],
        "tickets": [
            ticket(1, 1, "Tôm sú đông lạnh", 60, (50, 40, 20), 12, 5, "VIP", "2026-10-03T07:30", "2026-10-03T15:00")
        ],
    },
    {
        "id": "03_email_2lo",
        "about": "1 file 2 ticket (TC4): lô 1 inch/lb + 'gấp' + 'mai' (TC7, suy luận); lô 2 thiếu liều + giờ trả (TC3)",
        "pages": [
            email(
                "Yêu cầu chiếu xạ — Lô 1",
                "Chào anh chị, bên em gửi 50 thùng tôm đông lạnh, thùng 20 x 16 x 12 inch, mỗi thùng nặng 22 lb. "
                "Hàng đến 7h sáng mai. Nhờ bên mình làm gấp giúp em, cần trả trước 14h mai nhé. Liều: 5 kGy.",
            ),
            email(
                "Yêu cầu chiếu xạ — Lô 2",
                "Gửi thêm 200 thùng vật tư y tế (găng tay), thùng 50 x 40 x 30 cm, 12 kg/thùng. "
                "Hàng đến 13:00 ngày 03/10/2026. Liều và giờ trả em sẽ báo sau.",
            ),
        ],
        "tickets": [
            ticket(
                1,
                1,
                "tôm đông lạnh",
                50,
                (50.8, 40.64, 30.48),
                9.98,
                5,
                "URGENT",
                "2026-10-02T07:00",
                "2026-10-02T14:00",
            ),
            ticket(2, 2, "vật tư y tế (găng tay)", 200, (50, 40, 30), 12, None, None, "2026-10-03T13:00", None),
        ],
    },
    {
        "id": "04_phieu_thieu_lieu",
        "about": "Thiếu liều + giờ trả + ưu tiên (TC3)",
        "pages": [
            form(
                "PHIẾU YÊU CẦU DỊCH VỤ",
                "Hợp tác xã Trái Cây Sấy Đồng Tháp",
                "YC-2026-1001-04",
                [
                    ("Tên sản phẩm", "Xoài sấy dẻo"),
                    ("Số lượng", "60 thùng"),
                    ("Quy cách thùng", "50 x 35 x 30 cm"),
                    ("Khối lượng mỗi thùng", "11,8 kg"),
                    ("Giờ hàng đến", "13:00 ngày 02/10/2026"),
                ],
                note="Nhờ báo lại lịch giúp.",
            )
        ],
        "tickets": [ticket(1, 1, "Xoài sấy dẻo", 60, (50, 35, 30), 11.8, None, None, "2026-10-02T13:00", None)],
    },
    {
        "id": "05_phieu_tra_truoc_den",
        "about": "Giờ trả trước giờ hàng đến (TC8) — trích đúng giá trị, validator bắt lỗi",
        "pages": [
            form(
                "PHIẾU YÊU CẦU DỊCH VỤ CHIẾU XẠ",
                "Công ty TNHH Nông Sản Tây Nguyên",
                "YC-2026-1001-05",
                [
                    ("Tên sản phẩm", "Hạt điều rang muối"),
                    ("Số lượng", "100 thùng"),
                    ("Quy cách thùng", "40 x 30 x 20 cm, 10 kg/thùng"),
                    ("Liều chiếu yêu cầu", "10 kGy"),
                    ("Mức ưu tiên", "Khẩn"),
                    ("Giờ hàng đến", "14:00 ngày 04/10/2026"),
                    ("Giờ trả mong muốn", "10:00 ngày 04/10/2026"),
                ],
            )
        ],
        "tickets": [
            ticket(
                1, 1, "Hạt điều rang muối", 100, (40, 30, 20), 10, 10, "URGENT", "2026-10-04T14:00", "2026-10-04T10:00"
            )
        ],
    },
    {
        "id": "06_email_don_vi_anh",
        "about": "Email tiếng Anh, đơn vị inch/lb (TC7)",
        "pages": [
            email(
                "Irradiation request",
                "Hi team, we will send 40 cartons of dried mango slices, carton size 18 x 12 x 10 inch, "
                "20 lb per carton. Required dose 10 kGy. Arrival Oct 5, 2026 at 08:00, please return by 17:00 "
                "the same day.",
            )
        ],
        "tickets": [
            ticket(
                1,
                1,
                "dried mango slices",
                40,
                (45.72, 30.48, 25.4),
                9.07,
                10,
                None,
                "2026-10-05T08:00",
                "2026-10-05T17:00",
            )
        ],
    },
    {
        "id": "07_phieu_lieu_7",
        "about": "Liều 7 kGy ngoài danh mục — trích đúng giá trị trong ticket, không hỏi lại",
        "pages": [
            form(
                "PHIẾU YÊU CẦU DỊCH VỤ CHIẾU XẠ",
                "Công ty TNHH Gia Vị Minh An",
                "YC-2026-1001-07",
                [
                    ("Tên sản phẩm", "Bột nghệ vàng"),
                    ("Số lượng", "90 thùng"),
                    ("Quy cách thùng", "40 x 30 x 25 cm, 9 kg/thùng"),
                    ("Liều chiếu yêu cầu", "7 kGy"),
                    ("Mức ưu tiên", "Thường"),
                    ("Giờ hàng đến", "08:00 ngày 05/10/2026"),
                    ("Giờ trả mong muốn", "18:00 ngày 05/10/2026"),
                ],
            )
        ],
        "tickets": [
            ticket(1, 1, "Bột nghệ vàng", 90, (40, 30, 25), 9, 7, "NORMAL", "2026-10-05T08:00", "2026-10-05T18:00")
        ],
    },
    {
        "id": "08_phieu_2trang",
        "about": "1 ticket trải 2 trang (không được tách thành 2 lệnh)",
        "pages": [
            form(
                "PHIẾU YÊU CẦU DỊCH VỤ CHIẾU XẠ (trang 1/2)",
                "Công ty CP Hồ Tiêu Chư Sê",
                "YC-2026-1001-08",
                [
                    ("Tên sản phẩm", "Hạt tiêu đen"),
                    ("Số lượng", "80 thùng"),
                    ("Quy cách thùng", "45 x 35 x 30 cm"),
                    ("Khối lượng mỗi thùng", "15 kg"),
                    ("Liều chiếu yêu cầu", "10 kGy"),
                ],
                note="Tiếp theo ở trang 2.",
            ),
            form(
                "PHIẾU YÊU CẦU DỊCH VỤ CHIẾU XẠ (trang 2/2)",
                "Công ty CP Hồ Tiêu Chư Sê",
                "YC-2026-1001-08",
                [
                    ("Mức ưu tiên", "VIP"),
                    ("Giờ hàng đến", "08:30 ngày 03/10/2026"),
                    ("Giờ trả mong muốn", "17:00 ngày 03/10/2026"),
                ],
            ),
        ],
        "tickets": [
            ticket(1, 2, "Hạt tiêu đen", 80, (45, 35, 30), 15, 10, "VIP", "2026-10-03T08:30", "2026-10-03T17:00")
        ],
    },
    {
        "id": "09_phieu_vattu_yte",
        "about": "Vật tư y tế, 25 kGy, trả ngày hôm sau",
        "pages": [
            form(
                "PHIẾU YÊU CẦU DỊCH VỤ CHIẾU XẠ",
                "Công ty TNHH Thiết Bị Y Tế An Phát",
                "YC-2026-1001-09",
                [
                    ("Tên sản phẩm", "Găng tay y tế nitrile"),
                    ("Số lượng", "300 thùng"),
                    ("Quy cách thùng", "50 x 40 x 30 cm, 12 kg/thùng"),
                    ("Liều chiếu yêu cầu", "25 kGy"),
                    ("Mức ưu tiên", "Khẩn"),
                    ("Giờ hàng đến", "09:00 ngày 06/10/2026"),
                    ("Giờ trả mong muốn", "09:00 ngày 07/10/2026"),
                ],
            )
        ],
        "tickets": [
            ticket(
                1,
                1,
                "Găng tay y tế nitrile",
                300,
                (50, 40, 30),
                12,
                25,
                "URGENT",
                "2026-10-06T09:00",
                "2026-10-07T09:00",
            )
        ],
    },
    {
        "id": "10_email_traicay_gam",
        "about": "Email, khối lượng theo gam, ngày tương đối 'thứ Hai tới', không nêu ưu tiên",
        "pages": [
            email(
                "Gửi hàng chiếu xạ thanh long",
                "Chào anh, bên em có 150 thùng thanh long ruột đỏ, thùng 60 x 40 x 25 cm, mỗi thùng 12000 g. "
                "Liều 10 kGy. Xe tới xưởng 6 giờ sáng thứ Hai tới, cần nhận lại trước 12 giờ trưa cùng ngày.",
            )
        ],
        "tickets": [
            ticket(1, 1, "thanh long ruột đỏ", 150, (60, 40, 25), 12, 10, None, "2026-10-05T06:00", "2026-10-05T12:00")
        ],
    },
]

# Bản scan: raster lại bản văn bản số. `px` = cạnh dài ảnh (nhỏ → mờ), `quality` = JPEG, `rotate` = độ nghiêng.
SCAN_SAMPLES: list[dict] = [
    {"id": "11_scan_phieu_giavi", "source": "01_phieu_giavi", "px": 1100, "quality": 55, "rotate": 0},
    {"id": "12_scan_email_2lo", "source": "03_email_2lo", "px": 1000, "quality": 45, "rotate": 0.8},
    {"id": "13_scan_phieu_thieu_lieu", "source": "04_phieu_thieu_lieu", "px": 950, "quality": 40, "rotate": -1},
    {"id": "14_scan_email_don_vi_anh", "source": "06_email_don_vi_anh", "px": 800, "quality": 30, "rotate": 1.5},
    {"id": "15_scan_phieu_vattu_yte", "source": "09_phieu_vattu_yte", "px": 700, "quality": 25, "rotate": -2},
    {"id": "16_scan_tra_truoc_den_mo", "source": "05_phieu_tra_truoc_den", "px": 520, "quality": 15, "rotate": 2.5},
]


def answer_key() -> dict:
    """{sample_id: {kind, about, tickets}} — bản scan dùng đáp án của bản gốc."""
    by_id = {s["id"]: s for s in TEXT_SAMPLES}
    key = {s["id"]: {"kind": "text", "about": s["about"], "tickets": s["tickets"]} for s in TEXT_SAMPLES}
    for s in SCAN_SAMPLES:
        src = by_id[s["source"]]
        key[s["id"]] = {"kind": "scan", "about": f"Bản scan của {s['source']}", "tickets": src["tickets"]}
    return key
