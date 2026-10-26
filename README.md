# Rux Coding Pet

Biến robot LeTianPai Rux thành bạn đồng hành cho Codex, Claude Code và Kiro.
Android app hiển thị mặt, tên chat và thao tác đang chạy; tự chạy kịch bản chân/thân,
radar và giọng thông báo. Mỗi plugin độc lập, **mỗi chat có hàng đợi riêng**.
Rux giữ phiên đã chọn; không tự chuyển sang chat khác khi phiên đó hoàn thành.

Đã phát triển trên Rux AAD2C, Android 11 / API 30, GeeUI 1.2.12162.u. Tương thích
với firmware khác chưa được xác minh. Host hiện hỗ trợ macOS/Linux, Python 3.10+
(runtime dùng fcntl); build Android dùng JDK 17 và Android SDK 35.

## Cấu trúc source

```text
.
├── android/
│   ├── AndroidManifest.xml
│   ├── src/com/rux/assistant/
│   │   ├── MainActivity.java      # Mặt, tên chat, dòng thao tác
│   │   ├── ScenarioService.java   # RobotSDK, motor, audio, lịch lặp
│   │   ├── ScenarioClock.java     # Lease chuyển động và timer completed
│   │   ├── ScenarioStore.java     # Kiểm tra/lưu cấu hình AtomicFile
│   │   ├── MotionSequence.java    # Hành động 1 → hành động 2
│   │   └── SessionQueues.java     # Chọn phiên trên robot
│   └── assets/README.md           # Hướng dẫn nạp audio cục bộ
├── plugins/
│   ├── common/                   # Adapter, wire protocol, skill setup dùng để build
│   ├── README.md                 # Cài Codex / Claude Code / Kiro
│   └── PROTOCOL.md               # source/session/turn/sequence/activity
├── scripts/
│   ├── build.sh                  # Build APK, không cần Gradle
│   ├── build_plugins.py          # Xuất ba bộ plugin độc lập
│   ├── prepare_local_assets.py   # Nạp SDK/audio từ máy của bạn
│   ├── rux.py                    # ADB RPC
│   ├── chat_hook.py              # Hook/worker, dùng riêng từng chat trong plugin
│   ├── activity_summary.py       # Nhãn đọc/sửa tệp, không gửi nội dung file
│   ├── scenario.py               # Cấu hình/RPC prototype
│   ├── active_scenario.json      # Kịch bản mặc định, không có địa chỉ robot
│   ├── voices.json               # Metadata và nguồn các giọng
│   ├── build_catalog.py          # Web chọn mặt/động tác
│   └── catalog_server.py         # Máy chủ web loopback
├── tests/                        # Python unittest + policy Java/JVM
├── docs/                         # Kiến trúc, Android, plugin
├── vendor/README.md              # Nguồn RobotSDK; không kèm binary
├── Makefile
├── THIRD_PARTY_NOTICES.md
└── .gitignore
```

## 1. Chuẩn bị môi trường và tài nguyên

Cài Python 3.10+, JDK 17, Android SDK platform 35 / build-tools 35.0.0 /
platform-tools; cần unzip, zip và keytool. Thêm adb và JDK vào PATH.
Đặt `JAVA_HOME` và `ANDROID_HOME` theo vị trí cài trên máy của bạn.

Source không chứa file WAV, RobotSDK AAR hoặc APK tài nguyên của hãng. Nếu đã có
một bản Rux Assistant chạy được, nhập lại dependency từ bản đó:

```sh
python3 scripts/prepare_local_assets.py --from "/path/to/existing/Rux Assistant"
```

Hoặc chỉ rõ SDK và các file giọng do bạn cung cấp:

```sh
python3 scripts/prepare_local_assets.py \
  --sdk /path/to/RobotSdk-release.aar \
  --voices-dir /path/to/wav-files
```

Script kiểm tra các file trước khi copy; không copy kết nối ADB, tài khoản, log hay
keystore. Xem [tài nguyên audio](android/assets/README.md) và
[nguồn phụ thuộc](THIRD_PARTY_NOTICES.md). Tài nguyên đã nhập được .gitignore bỏ qua.

Bộ mặt cute được vẽ bằng Java. Web vẫn dùng được với mặt cute và mã chuyển động
khi chưa có clip hãng. Muốn xem trước biểu cảm gốc, nhập thêm APK tài nguyên từ robot:

```sh
python3 scripts/prepare_local_assets.py --from /path/to/existing/project --catalog
# Hoặc thêm --resource-apk /path/to/GeeUIResource.apk
```

Cần ffmpeg trong PATH khi tạo ảnh xem trước clip gốc. Không commit APK/clip của hãng.

## 2. Build và cài Android

```sh
bash scripts/build.sh
export ADB=/absolute/path/to/adb
export RUX_SERIAL=ROBOT_USB_SERIAL_OR_IP_PORT
python3 scripts/rux.py install
python3 scripts/rux.py status
python3 scripts/scenario.py sync
```

`RUX_SERIAL` nhận serial USB hoặc dạng IP:5555. Chỉ kết nối với robot đã cho phép USB
debugging. Chuyển sang Wi-Fi ADB qua kết nối USB đã được cấp quyền:

```sh
adb -s ROBOT_USB_SERIAL tcpip 5555
adb connect ROBOT_IP:5555
```

Build tự tạo **debug signing key mới trên máy đó**, lưu trong ignored build/.
Nếu robot có APK cũ ký bằng key khác, cập nhật có thể bị từ chối. Dùng đúng key của
bản cũ hoặc tự quyết định sao lưu/gỡ bản cũ; script không tự gỡ app/xóa dữ liệu.

Xem [hướng dẫn Android](docs/ANDROID.md) cho preset và giới hạn chuyển động.

## 3. Mở web chọn kịch bản

```sh
python3 scripts/build_catalog.py
python3 scripts/catalog_server.py
```

Mở http://127.0.0.1:8874/. Bật chế độ thử để thử từng lượt; bấm
**Lưu kịch bản vào Rux** để áp dụng. Mỗi trạng thái có hai hành động thân/chân nối
liền, radar, mặt và nhịp lặp. Chọn/tải JSON chỉ đổi bản nháp đến khi bấm lưu.
Web chỉ nghe loopback và kiểm tra Host/Origin/token. File token được tạo khi chạy,
không có token cố định trong source.

## 4. Build và dùng plugin

```sh
python3 scripts/build_plugins.py
```

Các ZIP và APK companion (nếu đã build Android) nằm trong `build/releases/`.
Ba plugin có runtime/config riêng; hàng đợi và heartbeat riêng cho từng chat.
Không cần cài plugin để build APK hoặc dùng web.

Xem [cài plugin](plugins/README.md), [tổng quan plugin](docs/PLUGINS.md) và
[giao thức](plugins/PROTOCOL.md). Chỉ dùng một integration cho cùng chat, tránh
bật đồng thời prototype hook và plugin. Source export không chứa .codex/hooks.json
của máy phát triển và không tự cài gì vào config tài khoản.

## Hành vi hiện tại

- Trạng thái working hiển thị **Đang suy nghĩ…**; idle hiển thị **Đang chờ Anh**.
- Chỉ completed tự về idle sau **60 giây**; gửi trùng/heartbeat không gia hạn timer.
- Không giới hạn thời gian suy nghĩ 5 phút. Mất heartbeat 45 giây dừng lặp motor,
  nhưng giữ mặt và phiên đã chọn; không tự chọn B khi A hoàn thành/mất kết nối.
- Mỗi nhịp chạy hành động 1 → 2, tối đa 3 giây mỗi hành động trong kịch bản chat.
  Tai và giọng phát một lần cho cả cặp. Dừng/sensor/đổi trạng thái hủy bước còn lại.
- Giọng hoàn thành theo asset đã nạp; câu mặc định là “Anh ơi, em xong rồi”.
- Dòng thao tác chỉ lấy loại tool và basename tệp; không gửi nguyên lệnh, prompt,
  nội dung file hoặc câu trả lời. Tool không có metadata tệp dùng nhãn chung.
- Điều khiển LED có nút thử, nhưng đổi màu trên firmware đã thử chưa được xác nhận;
  chưa bật LED tự động theo trạng thái.

## Kiểm tra

Sau khi nạp SDK/audio ở bước 1:

```sh
python3 scripts/build_catalog.py
python3 -m unittest discover -s tests -v
```

Các test policy Java dùng `JAVA_HOME/bin` hoặc javac/java trong PATH, không gọi
robot. Không cần đăng nhập tài khoản AI để chạy unit tests. Kiểm tra fixture và
policy không thay cho xác minh chat thật/firmware thật. Kiro IDE/V3 chưa được kiểm
tra trực tiếp; CLI validator có thể yêu cầu đăng nhập. Claude manifest có thể kiểm
tra riêng bằng `claude plugin validate <plugin-folder> --strict --json`.

## Đưa lên GitHub

Thư mục này không có .git, kết nối thiết bị, cấu hình người dùng, log, SQLite,
keystore, APK build, WAV hoặc SDK binary. Có thể dùng chính thư mục này làm repo:

```sh
git init -b main
git add .
git commit -m "Initial Rux Assistant source"
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

Mã nguồn dự án dùng [MIT License](LICENSE). SDK, firmware và audio bên ngoài tuân theo giấy phép riêng; xem [ghi chú thành phần ngoài](THIRD_PARTY_NOTICES.md).

## Tài liệu nguồn

- [Letianpai RobotSDK](https://cn.letianpai.com/?p=5915)
- [Demo RobotSDK](https://github.com/Letianpai-Robot/DemoForRobotSDK)
- [Codex plugins](https://developers.openai.com/plugins/build/plugins)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [Kiro hooks](https://kiro.dev/docs/hooks/)

## Cài APK trên firmware IncFS cũ

Luôn dùng `adb install --no-incremental -r <apk>` cho robot này. Helper rux.py đã ép cờ này; build.sh tắt tạo chữ ký v4/idsig. Một vùng cài incremental thiếu backing_store có thể kích hoạt kernel panic incfs_kill_sb trên firmware đã kiểm tra. Không dùng cài incremental hoặc dựa vào fallback tự động của adb.

## Nhãn suy nghĩ và chạy công cụ

Rux giữ `working` trong lúc xử lý: không có công cụ đang chạy thì hiện **Đang suy nghĩ…**, có nhãn thao tác thì hiện **Đang làm cật lực…** cùng dòng thao tác. `PreToolUse` đưa cùng lượt chat về working, `PostToolUse` không chuyển sang idle. Chỉ completed mới tự về idle sau 60 giây.

Codex `PermissionRequest` là bước kiểm tra trước quyết định cấp quyền, có thể được hệ thống tự xử lý; adapter ghi `PermissionCheck` và không gọi người dùng. Hook này chưa xác nhận được hộp thoại cấp quyền có thật sự đang chờ người dùng hay không. Công cụ hỏi đồng bộ `request_user_input`/`AskUserQuestion` chuyển sang attention, rồi quay về working khi trả về; câu hỏi bất đồng bộ không chặn công việc. Claude vẫn giữ mapping PermissionRequest riêng.

Tham chiếu hook: https://learn.chatgpt.com/docs/hooks
