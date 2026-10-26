# Kiểm tra bản source xuất ra

Kiểm tra ngày 26/10/2026 trên một bản sao tạm riêng, không build vào thư mục source
để đưa lên GitHub. SDK và WAV chỉ được nạp vào bản sao tạm để kiểm chứng.

| Bước | Kết quả |
|---|---|
| prepare_local_assets.py, kiểm tra/nạp phụ thuộc | Qua |
| build_catalog.py không có APK clip của hãng | Qua, vẫn có mặt cute và chuyển động |
| Python unittest + policy Java/JVM | 70 test qua |
| build.sh: javac, d8, aapt, zipalign, ký và verify APK | Qua |
| build_plugins.py: Codex / Claude / Kiro, bộ tổng, checksum | Qua |
| Claude Code plugin validate --strict --json | Qua |
| Quét IP/serial robot thật, đường dẫn user, ID chat đã dùng | Không có trong bản source |
| Quét binary dependency, keystore, log, SQLite, cache và .git | Không có trong bản source |

Các bước trên không gọi robot hoặc chạy một cuộc chat AI thật. Kiểm thử Kiro IDE/V3
trực tiếp và xác minh chuyển động trên firmware khác vẫn là các việc riêng.

Tài nguyên cục bộ, build output và log kiểm chứng không được kèm vào thư mục này.
