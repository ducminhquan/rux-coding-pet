# rux-session-queues-v1

Host RPC dùng ADB đã được xác thực. command/value/request là intent extras vào MainActivity (session-state, select-session) hoặc ScenarioService (session-heartbeat, sessions). value là base64 UTF-8 JSON, không phải shell command. Mỗi request có UUID; ACK được ghi qua logcat RuxAssistant với request ID.

## Envelope trạng thái

```json
{"source":"codex","session_id":"chat-a","turn_id":"turn-123","sequence":1,"state":"working","title":"Tên chat","quiet":true,"no_motion":false,"activity":"Đang đọc app.js…"}
```

- source: codex / claude / kiro.
- session_id: 1–200 ký tự ASCII chữ/số/._:-, riêng trong source.
- turn_id: tối đa 200 ký tự. Khi harness không cung cấp, adapter tạo ID mới ở UserPromptSubmit.
- sequence: số nguyên dương, tăng bền theo source/session qua cả state và heartbeat. Không reset counter khi vẫn dùng cùng session. Rux bỏ sequence cũ/trùng.
- state: working / attention / completed / idle / failed. Không chứa thông số motor; Rux tra kịch bản đã lưu.
- activity: tùy chọn, tối đa 80 ký tự nhãn thao tác. Chỉ hiện ở working; gửi chuỗi rỗng để xóa. Thay đổi activity không đổi context/episode. Mỗi hàng đợi giữ nhãn riêng; nhãn của B không xuất hiện khi A được chọn.
- title: tối đa 160 ký tự hiển thị. Không gửi prompt hay nội dung trả lời.
- quiet và no_motion: boolean; no_motion tắt cả hai hành động chân/thân và radar cho trạng thái đó.

ACK session-state `accepted=true stale=false selected=false` nghĩa là đã cập nhật hàng đợi chờ, không phải robot đã thực hiện động tác. `selected=true` chỉ cho biết hàng đợi hiện được chọn. SDK/hardware vẫn có thể lỗi sau ACK; xem RUN_* / MOTOR_OFF và trạng thái hàng đợi.

## Heartbeat

```json
{"source":"codex","session_id":"chat-a","turn_id":"turn-123","sequence":2}
```

Gửi qua session-heartbeat mỗi 15 giây. Lease 45 giây, riêng từng hàng đợi. Queue đang chờ có thể nhận `active=true` mà chưa được Rux chọn. Heartbeat không đổi lựa chọn, không tạo động tác và không mở lại queue bị Stop/sensor chặn.

## Liệt kê và chọn

- `sessions`: value rỗng hoặc base64 `{"offset":0}`. ACK chứa `data=<base64 JSON>` với `{queues:[...],next_offset:-1}`. Mỗi trang tối đa 2 mục để không vượt giới hạn dòng logcat. Dùng next_offset cho trang tiếp theo.
- `select-session`: base64 `{"source":"kiro","session_id":"chat-d"}`. Queue phải còn lease và chưa bị chặn.
- `pause`: ngắt motor/âm thanh, chặn tất cả episode đang có. Một turn/trạng thái mới mới có thể kích hoạt lại.
- `hold-sessions` / `release-sessions`: dùng cho chế độ thử web; giữ quyền điều khiển thủ công trên robot.

## Chính sách nằm trong robot

Sticky cho phiên đã chọn ở mọi trạng thái, kể cả completed, idle, bị Stop hoặc hết lease. Không tự chuyển sang phiên chờ. Chỉ chọn phiên hoạt động đầu tiên khi Rux chưa có lựa chọn; sau đó phải select-session tường minh. Hết lease dừng motor nhưng giữ mặt và khóa lựa chọn ở phiên đó. Chỉ completed tự hiển thị idle sau đúng 60 giây, độc lập heartbeat và không gia hạn khi gửi trùng. Working/attention/failed/idle không có timeout trạng thái hay giới hạn suy nghĩ 5 phút. Rux gộp các trạng thái chưa được theo về bản mới nhất, không chạy bù lịch sử cử động.

Inbox có tối đa 64 entry, chỉ trong RAM. Restart app xóa inbox và không tự tiếp tục động tác; cấu hình kịch bản vẫn lưu riêng. Không có source-specific persona hoặc thứ tự ưu tiên cố định Codex/Claude/Kiro trong bản này; có thể thay chính sách/phân vai trên Rux sau.

Lệnh set-state/heartbeat cũ còn tương thích cho prototype hiện tại. set-state cũ là điều khiển trực tiếp và chặn inbox hiện có; khi chuyển sang plugin, bỏ hook prototype để tránh hai giao thức tranh quyền hiển thị.
