"""Analytics context — ADC-007.

TODO(T-044): KPI từ plan version — on_time_rate, late_orders, total_delay_min, utilization{A, B}, avg_lead_time.
TODO(T-045): chế độ mô phỏng 1 line — chạy Scheduler với `lines=(Line.A,)` trên cùng seed; kết quả lưu thành
plan version `is_simulation`, không bao giờ ACTIVE (BR-11).
"""
