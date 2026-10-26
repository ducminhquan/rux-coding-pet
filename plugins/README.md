# Rux Assistant plugins 0.1.2

Ba bộ độc lập: Codex desktop, Claude Code, Kiro. Python 3.10+, Claude Code 2.1.295+ cho bản Claude, và ADB là dependency cục bộ; macOS/Linux (runtime dùng fcntl). Robot cần Rux Assistant hỗ trợ **rux-session-queues-v1**. Không gọi LLM hoặc dịch vụ TTS để phản ứng trạng thái.

## Kiến trúc

```text
Codex chat A → plugin Codex → queue A ─┐
Codex chat B → plugin Codex → queue B ─┤
Claude chat C → plugin Claude → queue C ─→ Rux SessionQueues → selected chat → ScenarioService → motor/face/audio
Kiro chat D → plugin Kiro → queue D ───┘
```

Mỗi plugin có bản runtime riêng, config riêng và data riêng. **Mỗi chat** có SQLite event queue, worker lock, sequence counter và heartbeat riêng; không có hàng đợi hay bộ chọn chung trên host. Khóa trong một chat chỉ ngăn chính chat đó gửi chồng. Rux chọn luồng nào để theo, dùng chung bộ kịch bản đã lưu trong robot.

Envelope: `{source, session_id, turn_id, sequence, state, title, quiet, no_motion}`. Source là codex/claude/kiro; số thứ tự tăng bền theo phiên. Giao thức qua ADB: session-state, session-heartbeat, sessions, select-session. Không mở cổng mạng mới.

Rux giữ phiên đang hoạt động; các phiên khác được nhận và giữ trạng thái mới nhất. Rux giữ nguyên phiên được chọn, không tự chọn B khi A kết thúc, hết lease hoặc bị dừng. Đổi phiên phải dùng select-session tường minh. Chỉ lần đầu chưa có lựa chọn mới tự chọn luồng đang hoạt động đầu tiên. Khi đổi phiên, trạng thái cũ được gộp, không phát lại một dãy cử động cũ. Stop chặn các episode hiện có; heartbeat không tự kích hoạt lại. Inbox tạm trong RAM tối đa 64 phiên, không tự tiếp tục động tác sau restart. Chính sách này ở robot; có thể thay sau mà không sửa plugin.

## Cấu hình kết nối — riêng từng plugin

Giải nén bộ tổng; giữ thư mục ổn định. APK companion được phát hành riêng tại `build/releases/rux-assistant-session-queues.apk`; cài APK companion lên robot trước khi dùng plugin. Không cần cài lại APK cho mỗi plugin. Với mỗi provider cần dùng:

```sh
python3 /path/rux-assistant-plugins/codex/scripts/rux_plugin.py configure --serial IP:5555 --adb /absolute/path/to/adb --project /absolute/project
python3 /path/rux-assistant-plugins/claude/scripts/rux_plugin.py configure --serial IP:5555 --project /absolute/project
python3 /path/rux-assistant-plugins/kiro/scripts/rux_plugin.py configure --serial IP:5555 --project /absolute/project
```

USB dùng serial thay IP:5555. `--project` có thể lặp nhiều lần; `--all-projects` là lựa chọn tường minh. Lệnh configure không đổi kịch bản trong robot. File mặc định: `~/.config/rux-assistant/<provider>.json`; data: `~/.local/share/rux-assistant/<provider>/sessions/<hash>/`. Config không nằm trong cache plugin, giữ nguyên khi update. `RUX_PLUGIN_CONFIG` cho phép chọn config khác khi kiểm thử.

Chỉ trạng thái completed tự về idle sau 60 giây; các trạng thái khác giữ nguyên, không có giới hạn suy nghĩ 5 phút. Mất heartbeat 45 giây dừng lặp motor nhưng giữ mặt và lựa chọn chat.

`doctor` kiểm tra config/dependency, không kết nối robot. `disable` tắt provider đó; lease trên robot tự hết sau tối đa 45 giây. Dùng nút Dừng trên web để ngắt ngay. Xem log tại từng thư mục session/worker.log.

## Codex desktop

Thêm thư mục bộ tổng làm local marketplace (CLI có sẵn hỗ trợ `codex plugin marketplace add`; xem `--help` của bản đang dùng), sau đó cài **rux-assistant** từ **rux-local** qua Plugins. Marketplace descriptor: `.agents/plugins/marketplace.json`. Có `.codex-plugin/plugin.json`, hooks và skill rux-setup.

```sh
codex plugin marketplace add /absolute/path/rux-assistant-plugins
codex plugin list --marketplace rux-local --available
```

Hook cần người dùng review/trust trong Codex trước khi chạy. Gói dùng lifecycle hooks nên phân phối/cài thủ công trên desktop, chưa dành cho public plugin directory. Không sửa `.codex/hooks.json` hiện có. Nếu cùng project còn hook prototype cũ, tắt hook prototype khi chuyển hẳn sang plugin để tránh hai bộ gửi đồng thời.

## Claude Code

```text
/plugin marketplace add /absolute/path/rux-assistant-plugins
/plugin install rux-assistant@rux-local
```

Chạy cấu hình kết nối cho provider claude ở trên, rồi mở chat mới. Có thể kiểm thử trực tiếp bằng `claude --plugin-dir /absolute/path/rux-assistant-plugins/claude`. Chỉ hook parent chat, bỏ qua tool events mang agent_id của subagent. PermissionRequest/permission notifications → attention; Stop → completed; StopFailure → failed; SessionEnd → idle. Không coi mọi tool error là kết thúc thất bại.

## Kiro

Kiro dùng hook definitions thay cho manifest plugin Codex/Claude. Trong gói kiro, chạy installer theo harness:

```sh
python3 /path/kiro/scripts/rux_plugin.py install-kiro --project /absolute/project --flavor cli-v2
# Hoặc --flavor cli-v3 / --flavor ide-v1
```

- CLI 2.x: tạo `.kiro/agents/rux-assistant.json`, không đổi default agent/permissions. Dùng `kiro-cli chat --agent rux-assistant`.
- CLI V3: tạo `.kiro/hooks/rux-assistant.json` với trigger/action PascalCase.
- IDE v1 when/then: tạo cùng file với when.type/then. Tài liệu Kiro hiện có hai dạng standalone; chọn đúng harness và kiểm tra Agent Hooks sau cài. Chưa xác minh chat trực tiếp trong IDE.

Installer từ chối ghi đè file khác nội dung; xóa riêng file Rux tạo để gỡ hook. Giữ nguyên profile/hook còn lại. CLI 2.x hook chỉ hoạt động trong agent rux-assistant; muốn giữ agent riêng, thêm các hook tương ứng vào agent đó sau khi review, không thay quyền tools.

Kiro có prompt/tool/stop hooks; chưa giả lập attention nếu harness không cung cấp sự kiện chờ duyệt. Nếu IDE không đưa session id vào hook, adapter dùng một luồng theo workspace (giới hạn: không tách được nhiều chat trong cùng workspace ở harness đó). Claude/Kiro không có turn_id trên mọi hook: adapter tự tạo turn ở UserPromptSubmit và dùng đến lần submit tiếp theo.

## Quyền riêng tư và lỗi

Chỉ lưu metadata sự kiện, ID phiên/lượt và tên chat hoặc tên project. Lưu thêm nhãn thao tác ngắn và basename tệp, ví dụ “Đang đọc app.js…”. Không lưu prompt/tool input thô, không đọc transcript hoặc last_assistant_message. Codex có thể đọc tên chat bằng app-server thread/read includeTurns=false; hai provider khác dùng session_title nếu host cấp, nếu không dùng tên project. Tên dự phòng không giả là tên chat thật.

Hook thiếu cấu hình, payload sai hoặc robot offline luôn trả `{}` và exit 0; không block tool, không tự duyệt quyền, không bắt agent tiếp tục. ADB lỗi nằm trong log worker riêng. Gói không chứa serial/IP của máy phát triển, voice recordings, keystore, account tokens hoặc lịch sử chat.

## Nguồn định dạng (đối chiếu 25/10/2026)

- Codex plugin + hook trust: https://developers.openai.com/plugins/build/plugins
- Codex event schema: https://learn.chatgpt.com/docs/hooks
- Claude manifests: https://code.claude.com/docs/en/plugins-reference
- Claude hooks: https://code.claude.com/docs/en/hooks
- Kiro standalone hooks: https://kiro.dev/docs/hooks/
- Kiro CLI migration/schema: https://kiro.dev/docs/cli/v3/hooks-migration/
- Kiro IDE when/then compatibility: https://kiro.dev/docs/chat/diagnostics/

## Trạng thái kiểm chứng

Đã kiểm tra Python/JVM và strict manifest bằng Claude Code 2.1.310. Kiro CLI validator có thể yêu cầu đăng nhập, nên chưa xác minh bằng chat Kiro thật; IDE và CLI V3 là cấu hình theo tài liệu, chưa chạy trực tiếp. Không cài vào tài khoản/provider thật khi chỉ yêu cầu đóng gói.

## Thông điệp công cụ (0.1.2)

PreToolUse cập nhật dòng thao tác dưới tên chat; PostToolUse xóa đúng tool đang hiện. Tool use ID giúp Post của tool cũ không xóa tool mới. Stop/đổi turn xóa thông điệp. Read/Edit lấy basename tệp; shell chỉ phân tích các lệnh đọc/tìm/kiểm tra trong allowlist, không gửi nguyên lệnh, tham số bí mật hay nội dung file. Công cụ bọc mã/không cấp tên tệp dùng nhãn chung; không suy đoán file từ mã nguồn nhúng. Cập nhật activity giữ nguyên episode, không chạy lại động tác hoặc gia hạn timer completed.
