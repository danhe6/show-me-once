# 开发日志（每次改动都记在这里，最新的在最上面）

格式：日期 时间 · 改了什么 · 为什么 · 涉及文件 · 怎么回退（备份位置）

---

## 2026-11-04

### 13:30 · 收尾：修 bug、演示视频、README、推送 GitHub
- Bug：学生首页的 "Go"（打字）按钮调用的 typed() 在 11/2 11:55 改录音代码时被误删，打字无效。已恢复（static/index.html）。
- 整理演示数据：归档测试任务（Use a computer、Learn AI、hot pot ×2、Ask ChatGPT、Take my pills、重复的泡茶和叠衣服），清空学生请求和练习记录；保留"泡茶"和"叠 T 恤"两个样例任务。
- 演示视频 show-me-once-demo.mp4（2:39，1920×1080，存在 ~/Documents/）：
  - 老师建任务（追问、步骤、安全标记）：浏览器里真实运行、真实模型输出的截图。
  - 学生练习：Playwright 录的真实前端，后端是回放测试中模型输出的 mock，镜头用测试图片；画面上一直标注 "Interface recording · replayed model output · test images as the camera"。
  - 老师数据表和 agents 页：mock 里的 4 次练习是虚构数据，画面一直标注 "Sample data · for illustration"。
  - 旁白 Kokoro am_michael，教练 Kokoro af_heart；结尾写明"开发者演示，尚未在学生身上测试"。
- README：加上镜头画面标注、免按键对话、追问、Kokoro 声音、"学生说完成+镜头认可"三种确认方式、中文限制、速度限制；运行步骤加 tts_setup.py。
- sync_public.py：加入 src/tts.py、tts_setup.py、smoke_clarify.py、smoke_mark.py 和叠衣服样例任务；requirements 加 soundfile、kokoro-onnx；.gitignore 排除模型和语音缓存。

## 2026-11-02

### 13:25 · 卡在"抚平"这一步、太啰嗦、不接受学生说做完了
- 日志：第 2 步 "Smooth shirt with both hands" 没有看得见的结果，模型一直 working、从不 done，每 8 秒换一句 "keep smoothing"；学生说 "Can we continue?" 只被回了一句话，没推进。
- 改：
  1. 学生说做完/要继续 → `coach.answer` 返回 claims_done；画面不矛盾且这一步无危险 → 进入下一步，记为 verified="agreed"（数据表 ◎，算独立）。有危险的步骤仍要镜头或老师确认。
  2. 动作类步骤（无危险）做了 20 秒以上、≥4 次 working、没出错 → 自动算完成。
  3. 每一步的提示只说一次（开始 5 秒后）；停 20 秒没动再提醒一次；做错/做早/危险/看不清太久照常立即说。
  4. PLAN_PROMPT 规则 5：每一步必须改变镜头能看到的东西，抚平/整理/检查/等待并进产生结果的那一步。
- 叠衣服任务（be99304548）：第 1、2 步合并成 "Lay shirt flat, front side down."，共 7 步，依赖重排；清掉今天的测试记录。
- 文件：src/coach.py、app.py、static/index.html
- 回退：data/out/app_coach_v14.bak.py、coach_v12.bak.py、index_coach_v16.bak.html

### 13:05 · 镜头画面上实时标注（圈 + 箭头）
- Dan 提出：既然能看懂画面，就在镜头画面上画简单的箭头标注该怎么做，做实时视觉交互。
- 做法：WATCH / WATCH_FLEX 提示词增加 "mark"：要动的东西在画面的位置（百分比）+ 该去的位置 + 1–3 个词的标签；和判断是同一次调用，不加延迟。`coach._mark()` 清洗坐标。
- 前端：镜头上叠一层 SVG（.ov）：脉动的青色圆圈 + 虚线流动的弯箭头 + 标签；done 时清掉；4 秒没新标注自动消失。前置镜头画面是镜像，x 翻转。
- 关键修正：视频是 cover 裁切显示的，grab() 现在按屏幕上显示的那一块裁切后再送模型，坐标才能对上。
- 测试 job 109（图卡当镜头）：茶包被圈住、箭头指向杯子；水壶被圈住。位置准确。
- 限制：1.5–3 秒更新一次，不是平滑 AR；偶尔会圈偏。SAM 精准轮廓版本留到视频拍完后再考虑。
- 文件：src/coach.py、static/index.html、smoke_mark.py（新）
- 回退：data/out/coach_v11.bak.py、index_coach_v15.bak.html

### 12:45 · 中文开关隐藏（SHOW_LANG=false，默认英文）
- Dan 决定测试和演示都用英文。中文代码保留，static/index.html 里 SHOW_LANG 改 true 即恢复。

### 12:25 · 开始前指导摆放；中文模式
- 摆放：READY 提示词新增 "view"（太近/太远/没对着桌子/太暗 → 一句具体调整，如 "Tilt the phone down toward the table"）。开始前循环最多 8 轮：画面不对先说怎么调，再看东西齐不齐，每轮给 5 秒调整。练习中"看不清"也用模型给的具体建议。
- 中文：学生首页加 中文/English 开关（localStorage）。`coach.lang_note()` 拼进 intent/ready/watch/watch_flex/answer 五个提示词；步骤和标题用 Spark 翻译一次缓存在 task.json["i18n"]（步骤改了自动重翻），POST /sessions 返回 texts/title_l；固定句子（问候、停下、夸奖、衔接）全部双语；Kokoro 中文声音 zf_xiaoxiao（lang=cmn）。
- 测试 job 105：翻译准确（"把 T 恤平放在桌子上。/ 放平"）；中文判断、接话、摆放指导都正常。**Meta 语音识别不支持中文**（Kokoro 中文音频送去识别得到乱码），所以中文模式用浏览器自带识别（webkitSpeechRecognition, zh-CN），不可用时打字。
- 文件：src/coach.py、src/tts.py、app.py、static/index.html、smoke_zh.py（新）
- 回退：data/out/app_coach_v13.bak.py、coach_v10.bak.py、index_coach_v14.bak.html

### 11:55 · 练习时能对话；判断更顺、提示更像老师
- Dan 实测叠衣服：17 秒只判断 6 次（2–4 秒一次），结果在 done 和"看不见手"之间跳，"连续两次 done"凑不齐；提示在"铺平"和"让我看手"之间交替；开始后 12 秒内设计成不说话，所以几乎没有语音互动。
- 对话：练习时麦克风常开（earLoop）。原始音频进 0.6 秒环形缓冲，学生一开口就从缓冲开始录，说完停顿 1.3 秒自动结束，转成 16k WAV 送识别（不再用 MediaRecorder，开头不会丢）。教练自己在说话时不听。学生说的不只是问题，陈述（"我放桌上了"）也会被接话并带到下一步：ANSWER 提示词改成"像站在旁边的老师接话"，并传入已完成/可做的步骤（app.py /ask 多了 done 参数）。
- 判断：最近 3 次里 2 次 done 就算过；"看不清"不再否定之前的 done；提示在开始 5 秒后就说；"看不清"只在连续 10 秒后说一次固定的话（"Move the phone back a little…"），不再来回换。
- 速度：每次送 2 帧、512px。
- 开始前的提示改成"把手机垫高一点、微微朝下"。
- 文件：static/index.html、src/coach.py、app.py
- 回退：data/out/app_coach_v12.bak.py、coach_v9.bak.py、index_coach_v13.bak.html

### 11:30 · 批准即分配；语音输入不再切头切尾
- Dan 实测：老师批准了 "Fold a T-shirt" 但没分配学生，学生端看不到。改成 Approve 时没选人就自动分给全班（app.py edit_task）。已把 be99304548 手动分给三个学生。
- 语音：转写结果是 "Learn"/"Learn ai"（说的是 "I want to learn AI"），头尾被切。原因：点按钮后麦克风要 ~1 秒才开始录，用户已经在说；结束要再点一下。改成：
  - 点 "Tap to start"（和进入练习）时就提前打开麦克风，之后按下立刻开始录（static/index.html openMic/listen）。
  - 停顿自动结束：听到说话后安静 1.3 秒自动停；6 秒没人说也停；最长 12 秒。按钮上有音量条。
  - 服务端转 WAV 时头尾各补 0.4 秒静音，并打印音频长度和耗时（app.py transcribe）。
- 回退：data/out/app_coach_v11.bak.py、index_coach_v12.bak.html

### 11:05 · 目标太宽先追问；电脑/手机任务不再拒绝
- 为什么：Dan 实测老师端输入 "learn AI" 被拒绝，"use the computer" 拆出来的步骤太泛（像开机，不像用电脑）。根源是没先问清楚要做什么。
- 追问：新增 `coach.clarify()` + `POST /api/tasks/clarify`（Spark）。目标够具体（make a cup of tea）→ 直接拆步骤；太宽 → 返回一个问题和 3–5 个具体选项（本身就是可用的目标），老师点一个或自己输入，也可以"anyway"直接拆。
- 电脑/手机任务：PLAN_PROMPT 规则 9 改成允许，要求写到具体 app、按钮、屏幕文字，done_state 是屏幕上出现什么。拒绝只针对吃药、电动工具等，拒绝时要给原因 + 替代建议。Steps 页对屏幕类任务提示"镜头看不到屏幕，由老师确认"。
- 实测 job 098："use the computer" → 发邮件 / 上网课 / 查公交 / 填求职表；"learn AI" → 问 ChatGPT 作业 / 用 AI 写邮件 / 列购物清单 / 练面试；"cleaning" → 擦桌子 / 扫地 / 倒垃圾 / 拖地；"make a cup of tea" 直接通过。"Ask ChatGPT a question" 拆出 7 步，每步写到具体按钮和屏幕；"take my pills" 拒绝并建议改成"倒杯水交给照顾者"。
- 文件：src/coach.py、app.py、static/index.html、smoke_clarify.py（新）
- 回退：data/out/app_coach_v10.bak.py、coach_v8.bak.py、index_coach_v11.bak.html

## 2026-11-01

### 21:15 · 学生听到的声音换成 Kokoro（开放权重 TTS，本机生成）
- 为什么：手机自带声音太机械；Meta 没有开放 TTS。Kokoro-82M 开放权重（Apache-2.0），在 Mac CPU 上就能跑，也对上 Open weights 奖项。
- 安装：tts_setup.py（Dan 在终端运行一次）：pip install kokoro-onnx soundfile；模型 kokoro-v1.0.onnx（325 MB）+ voices-v1.0.bin 放在 data/tts_model/（已加入 .gitignore，公开仓库 README 要写下载步骤）。
- 代码：src/tts.py（新）`speak(text)` 返回 WAV，按文本哈希缓存到 data/coach/tts_cache/；app.py 新增 `GET /api/tts?text=&speed=`、`GET /api/tts/status`，启动时后台预加载模型。
- 前端：say() 优先请求服务器声音，失败自动退回手机自带声音；当前步骤旁"接下来可做"的两步提前生成；老师首页 Voice 区显示当前声音。
- 修了一个死锁：speak() 持有 Lock 再调用同样要拿锁的 _engine()，第一次请求永远挂住。改成 RLock + 先取引擎再加锁。
- 实测：第一次生成一句 1.8 秒（含模型已预热），缓存命中 7 毫秒。默认声音 af_heart，等 Dan 试听后定。
- 回退：data/out/app_coach_v9.bak.py、index_coach_v10.bak.html；删掉 src/tts.py 和 app.py 里的 tts 两处即可。

### 20:55 · 学生可以打字；说话像真人老师；依赖推断不再摇摆
- 打字：学生首页和练习中的 Ask 都加了输入框，说话和打字都可以（static/index.html）。
- 说话风格：src/coach.py 新增 VOICE（像站在旁边的耐心老师：短句、具体的夸奖、不说 wrong、一次一个意思），拼进 WATCH、WATCH_FLEX、READY、ANSWER、INTENT 五个提示词。镜头判为 done 时模型顺便给一句具体夸奖（praise）。
- 衔接：做完一步后，先说具体夸奖，再自然带到下一步（"Nice, the kettle's full. Now let's put it on its base."），每三步叫一次名字。老师录过音的步骤：夸完接老师的录音。结束语也带名字。语速 0.92，音调略高。
- 实测（job 086）：检查桌面 → "I see the kettle and mug. Let's find a spoon and tea bag."；问能不能跳步 → 委婉拒绝并让问老师。
- **发现并修复**：依赖推断（infer_order）单次结果会摇摆。10/28 说 1、2 步互不依赖，今晚一次却把 8 步连成固定链。改成：要求每条依赖给出物理原因，过滤掉"习惯/通常/顺序"类理由，跑两次取交集，再做传递闭包。order_test.py 跑 3 遍结果一致：1–3 步任意顺序，倒水等烧开，泡茶等倒水。代价是约 50 秒，所以旧任务改成先按固定顺序、后台推断（app.py get_task）。
- 文件：static/index.html、src/coach.py、app.py、order_test.py（新）
- 回退：data/out/index_coach_v9.bak.html、coach_v7.bak.py、app_coach_v8.bak.py

### 20:38 · 学生首页先显示 "Tap to start"（手机上没声音）
- 为什么：Dan 实测听不到声音。手机浏览器规定，页面要先被点一下才能用语音朗读，所以打开页面时自动说的问候被拦了。
- 改了什么：学生首页先显示一个大按钮 "Tap to start"，点它时在同一次点击里读出问候，之后的语音都能正常播放。
- 文件：static/index.html。不用重启服务，刷新页面就能生效。

### 20:30 · 准备提交：公开仓库副本 + 新 README + 演示剧本
- 停掉了 10/28 起一直开着的公网链接（job 082）。
- 新建 ~/Documents/show-me-once：只放教练相关文件（app.py、serve.py、src/coach|agents|safety|spark.py、static/index.html、smoke_*.py、docs/DEVLOG.md、样例泡茶任务和 3 个样例学生）。不含 .env、学生练习数据、镜头日志、旧药箱代码。
- 新增 sync_public.py：开发目录改完后运行一次，就把公开副本更新到最新（样例任务会自动清掉学生数据、录音、照片）。
- README.md（英文）重写成现在的产品：问题、功能、多 agent、用到的 Meta 模型、诚实的局限、运行方法。另加 LICENSE（MIT）和 .gitignore。
- serve.py：输出改成英文；自动创建 jobs/ 文件夹（公开副本里没有这个文件夹，原来会报错）。开发目录同步了这一版。
- check_public.py：确认公开副本能独立运行（job 084）：首页、任务、学生、依赖推断、图卡都正常，一次真实镜头判断也正常。
  - 发现：AI 图里水壶底座靠近水，被判为 unsafe（符合"电和水"规则）。拍摄时底座要放得离水槽远一点。
- 产品文档顶部新增"11/1 最终版：3 分钟 Demo 剧本与拍摄清单"，旧剧本标为过时。

## 2026-10-28

### 14:12 · 灵活顺序：agent 认出学生在做哪一步，不再按固定顺序判断
- 为什么：Dan 认为做事没有固定步骤（泡茶可以先烧水，也可以先拆茶包）。保留"固定顺序"给需要固定流程的学生，老师按任务选，默认灵活。
- 数据：每一步加了 `needs`（必须先做完的步骤，0 开始的下标），只记真正的依赖（物理上需要或安全原因）。
  - 新任务：plan 时让 Wonder 一起写。
  - 旧任务：第一次打开时用 `coach.infer_order()` 推断。
  - 步骤文字改了或 Tuner 拆步：先退回固定顺序，后台重新推断。
  - 任务新增 `order` 字段：flex / fixed，PATCH 可以改。
- 判断：灵活模式用 `coach.watch_flex()`，把"已做完 / 现在可以做 / 必须等"三组步骤一起交给 Spark。模型返回学生在做哪一步（step）和状态（idle / working / done / too_early / wrong / unsafe / unclear）。只能勾掉"现在可以做"的步骤，依赖没满足就判 too_early 并提示先做什么。固定模式还用原来的 `watch()`。
- 学生端：
  - 维护一组做完的步骤（DONE）。模型认出学生在做另一个可做的步骤时，自动切过去，不念出来打断。
  - 每一步的错误、提示、计时分开记。
  - 进度点显示哪些做完了；提示下方显示"Or you can: …"。
  - 做完一步后，从"现在可以做"里挑下一个；依赖数据有问题时，兜底挑剩下没做的。
- 老师端：Steps 页新增"Order"选项（Any order that makes sense / Same order every time）；每步显示"After step X"或"Can be done any time"。
- 测试 job 078（泡茶副本）：
  - 推断依赖：1 和 2 互不依赖；3 在 2 之后；6 在 2–5 之后。
  - 什么都没做时装水 → 认成第 2 步，done。
  - 什么都没做时倒水 → too_early。
  - 1–5 做完后倒水 → working。
  - 每次 2.1–2.6 秒。
- 文件：src/coach.py、app.py、static/index.html、smoke_flex.py（新）
- 回退：data/out/app_coach_v7.bak.py、coach_v6.bak.py、index_coach_v8.bak.html

### 13:20 · 清掉泡茶任务的假数据
- 删掉 ac801abc93 的全部 6 条记录：4 条 seed_manual 造的老师记录、Dan 10/28 的测试、Claude 的浏览器测试。Maya 和 Leo 的提示级别恢复成初始值，清空 agent 时间线、汇报和修改方案。
- 证据小图移到 data/out/_old_evidence/tea_1028。watch_log.jsonl 保留（Dan 的真实测试判断，用来排查识别问题）。
- 回退：data/out/task_tea_before_clean_1028.bak.json

### 12:15 · 多 agent：Coach → Monitor → Tuner（老师批准）→ Analyst
- 为什么：Dan 想用多个 agent 分工。原则是每个 agent 必须干实事；数字由代码算；改东西要老师批准；不让 AI 自动改代码。
- 分工（新文件 src/agents.py）：
  - Coach（已有，Spark）：练习时实时看、提示、回答。
  - Monitor（纯代码）：读 watch_log，统计每一步的判断次数、看不清比例、平均耗时、跳步/危险/报错。判为有问题的条件：看不清 >35%（至少 6 次判断）、平均 >4.5 秒、≥3 次报错、出现过危险动作。
  - Tuner（Wonder）：针对有问题的一步，提一个修改方案：rewrite（改写"做完的样子"）、split（拆成两步）、camera（换手机位置）、photo（补参照照片）、safety（改安全做法）。老师点 Apply 才生效。拆步时，旧记录的步骤号和每个学生的提示级别会跟着后移，数据表不会错位。
  - Analyst（Wonder）：读代码算好的 facts（每步代码、掌握情况、标记、镜头有问题的步骤），写汇报、做得好的、需要支持的、下周建议和一句 IEP 话术。提示词要求只能用 facts 里的数字。
- 自动串联：每次练习结束（`/sessions/{id}/end`）后台跑 Monitor → 有问题就跑 Tuner → 跑 Analyst。每个 agent 做了什么写进 task["agent_log"]。
- 接口：`GET /api/tasks/{id}/agents?student=`、`POST /tune?step=`、`POST /analyse?student=`、`POST /proposals/{pid}/apply|dismiss`
- 老师端：任务页新增"Agents"标签。从上到下：流程图、待批准的修改、Analyst 汇报（可复制 IEP 句子、可刷新）、每步镜头统计（可"Ask Tuner"）、agent 时间线。标签名改短：Data / Record / Agents / Steps。
- 测试 job 075（泡茶副本 + 模拟镜头记录：第 1 步 10 次里 6 次看不清）：
  - Monitor 标出第 1 步（60% 看不清）。
  - Tuner 判断"茶包在杯子里镜头看不到"，提议把步骤改成"Drop tea bag into mug, tag out."，让镜头检查茶包标签挂在杯沿外。Apply 后数据表正常。
  - Analyst 汇报只用了 facts 里的数字。整条链跑了 17.7 秒。
- 文件：src/agents.py（新）、app.py、static/index.html、smoke_agents.py（新）
- 回退：data/out/app_coach_v6.bak.py、index_coach_v7.bak.html（删除 src/agents.py）
- 文件同步注意：commit 工具如果反复用同一个暂存文件名，可能写进旧内容。以后每次用新的暂存文件名，写完用 md5 核对。
- 注意：泡茶任务里 Maya 的"最新一次 0%"来自浏览器测试留下的那条记录（还有 seed_manual 造的假数据），都要删。

### 11:55 · 改成对话式教练（学生端）+ 图片变成可选
- 为什么：Dan 提出既然有摄像头，就让 AI 先问"今天想做什么"，再看着一步步指导。这样就不用纠结图片画得对不对。
- 保留的原则：AI 只从老师批准、分给这个学生的任务里选，不当场生成步骤给学生做（安全、步骤每次一样、IEP 数据可比）。学生说了没有的任务，记成请求交给老师。
- 学生端：
  - 首页是 AI 气泡，说"Hi Maya! What do you want to do today?"；大按钮"Tap and tell me"（最长 8 秒）；下面"Or pick one"列出任务，给不说话的学生直接点。
  - 说完 → 语音转文字 → `POST /api/intent` → 用 Spark 匹配任务。匹配到：说"Great, let's make tea together!"，直接进入练习。匹配不到：说"I'll ask your teacher to add it."，写进 data/coach/requests.json。
  - 开始前查桌面：`POST /api/tasks/{id}/ready`，最多看 5 次，说"我看到了 X，请把 Y 拿来"。东西齐了自动开始，也可以点"Let's start"。
  - 练习中加了"Ask"按钮：学生说出问题 → `POST /api/tasks/{id}/ask`，看着当前画面回答一句（不能跳步、不给医疗建议）。
  - 没有图片的步骤只显示大字和语音；有老师照片或 AI 图时仍然显示。
- 老师端：
  - 新建任务默认"No pictures: live coach"（media=live，不用拍照就能 Approve，照片可选）。
  - 首页新增"Students asked for"，点"Make it"直接用学生的原话新建任务。
- 测试 job 070：
  - "um I want tea" / "can I make some tea please" → 泡茶。
  - "fold my laundry" / "cut an apple" → 交给老师。
  - 查桌面能说出看到和缺的东西。
  - 问"where is the tea bag"，回答"The brown tea bag is in your right hand."
  - 问"can I skip"，回答"No, please do not skip…"
- 小修：查桌面时把开关、底座算作水壶的一部分（11:57）。
- 文件：app.py、src/coach.py、static/index.html、smoke_live.py（新）
- 回退：data/out/app_coach_v5.bak.py、coach_v5.bak.py、index_coach_v6.bak.html
- 注意：job 069 失败，是因为 app.py 第一次没写进去，重新写入后 job 070 通过。另外：文件同步工具偶尔报"已写入"但内容是旧的，改完要在 Mac 上 grep 确认。

### 08:45 · 练习默认用前置摄像头（可切换）
- 为什么：很多动作要两只手做，手机得立在学生面前，从前面看。
- 改了什么：练习页默认前置摄像头，画面左右镜像，看起来像照镜子；右上角按钮可以切前置/后置，选择存在这台设备上。前端送 `view=front|back`，`coach.watch()` 的提示词说明手机从正面对着学生（学生的右手在画面左边），只看桌上的手和物品，不看脸和背景。
- 文件：static/index.html、app.py、src/coach.py
- 回退：同 08:35 的备份

### 08:35 · 按 Dan 手机实测反馈改了四件事（实时看动作、防跳步+监控、声音、统一安全规则）
起因：Dan 实测：①镜头完全看不懂他在做什么，也不给提示；②声音太像 AI；③图片安全问题每次都要单独改；④学生能随便跳步，老师不在场也不知道做没做对。

1. **镜头一边看一边提示**（src/coach.py `watch()` 替换旧 `judge()`；旧函数保留为兼容外壳）
   - 以前：每 2.5 秒送 1 帧，只问"做完没有"。
   - 现在：前端一直拍，每次送最近 3 帧（约 0.6 秒一帧），模型看动作变化。如果老师给这一步拍过真实照片，就一起送去当参照。
   - 返回 `seeing`（"You are …"，显示在镜头画面下方）、`status`（not_started / working / done / wrong / ahead / unsafe / unclear）、`hint`（下一个小动作）、`evidence`。
   - `ahead` = 跳到下一步了，提示先回来做这一步。`unsafe` = 按安全规则看到危险动作，学生端红屏"Stop. Put it down. Wait for your teacher."，并自动通知老师。
   - 说话变少：同一句 20 秒内不重复，两次提示之间至少隔 8 秒；出错或危险时立刻说。
   - 每次判断都写进 data/coach/watch_log.jsonl，方便查"为什么没认出来"。
   - 实测（真实 Spark）：1.2–2.8 秒一次。"放茶包"判为 done；拿第 2 步的画面去测第 1 步，判为 ahead，提示 "Put tea bag in mug first"。
2. **不能跳步 + 老师监控**（app.py、static/index.html）
   - 删掉学生自报的 "I did it"。每一步只能由两种方式确认：镜头连续两次看到做完，或老师确认。老师确认有两种：在学生手机上按住 2 秒，或在老师端点 "Step N done ✓"。
   - 新接口：`GET /api/live`（谁在练、第几步、镜头看到什么、求助/危险/卡住/跳步提醒）、`GET /api/live/{sid}/frame.jpg`（最新一帧，只存在内存里）、`POST /api/live/{sid}/confirm|help|confirmed`。
   - 老师首页新增 "Practicing now" 卡片，每 2 秒刷新一次。
   - 每一步记录 `verified`（camera / teacher / self），并存一张"做完那一刻"的证据小图（tasks/<id>/evidence/<session>_<step>.jpg）和异常标记 `flags`（ahead / wrong / unsafe）。
   - 数据表：◉ = 镜头确认，T = 老师确认，? = 未确认；有红点表示有跳步或危险记录。点格子可以看证据小图。
   - 规则：未确认（self）的步骤不再算 I（独立）。自动备注里写明"几步镜头确认、几步老师确认"。
3. **声音**
   - 老师可以给每一步录自己的声音（Steps 标签 → "Record your voice"，最长 8 秒），学生端优先播放老师的录音（`POST/DELETE /steps/{i}/voice`，`GET /voice/{name}`）。
   - 没有录音时，自动挑这台设备上最自然的声音（Premium / Enhanced / Natural 优先，排除搞怪声音），语速 0.95。老师首页可以手动选声音并试听。
   - iPhone 需要先下载 Ava 或 Zoe（Premium）声音。
4. **统一安全规则**（新文件 src/safety.py）
   - 四类危险：高温、刀具、电和水、清洁剂。每类都写好"拆步骤怎么写、画图怎么画、查图判什么为不安全、练习时看到什么要叫停"。
   - 拆步骤（PLAN_PROMPT）、画图（NOHANDS）、查图（CHECK_CARD）、练习看镜头（WATCH）全部从这一个文件取规则。以后改规则只改这里。
   - 每一步自动算出 `hazards`。命中的步骤：AI 图不画手；练习时提示"老师要在旁边"；Steps 标签显示 "Teacher nearby for this step"。
- 文件：src/safety.py（新）、src/coach.py、app.py、static/index.html、smoke_watch.py（新，冒烟测试）
- 回退：data/out/app_coach_v4.bak.py、data/out/coach_v4.bak.py、data/out/index_coach_v5.bak.html（删除 src/safety.py 即可）
- 测试：job 064 smoke_watch.py 全部通过；浏览器里验证了无镜头时显示"老师按住确认"，老师端远程确认后学生端自动进入下一步。
- 注意：浏览器测试在泡茶任务里给 Maya 留下了 1 条测试记录（第 1 步，老师确认）。之后和之前的假数据一起删。
- 服务重启了（job 065/066），新链接见当天对话。

### 08:15 · 建立本日志
- 以后每次改代码都在这里加一条。

---

## 2026-10-27（第 2 天）方向与主要改动

### 方向定稿：给特教老师的"教学 + 数据采集"工具
- 一句话：帮特教老师教会学生生活技能，并把学生每一步的表现自动记录成 IEP 能直接用的数据。
- 用户：特教教室 / 生活技能 / 转衔课程的老师（主要用户），学生（受益人）。
- 不做：IEP 系统本身、阅读数学等学科、行为评分、存视频、AI 写 IEP。
- 依据：r/specialed 老师回复（数据录入麻烦、老师成了系统间的"搬运工"、想要快和现代的界面、对 AI slop 反感）；研究（分步视频提示有效但只有 26% 老师在用；AFIRM 任务分析数据表）。
- 之前的"药箱扫描"方向因比赛禁止"AI 医疗建议"而放弃，代码保留在 app_cabinet.py / static/cabinet.html。

### 后端 app.py（备份：data/out/app_coach_v1/v2/v3.bak.py）
- 任务：POST /api/tasks（goal + 可选照片 + media=photos|ai + style），Spark 看照片读出物品和按钮，Wonder 按特教规则拆步骤（每步一个动作、≤8 词、可观察的结束状态、安全提示、分段）。
- 图卡（media=ai 时）：先画统一参考图，每步两帧（动作前→动作中）做 2.6 秒小动画；危险步骤只画物品不画手；Spark 核对，危险图最多重画 3 次，仍危险则锁住不能 Approve。
- 引导拍照（默认，media=photos）：POST /api/tasks/{id}/steps/{i}/photo，照片跟着步骤走，学生端直接看真实照片。POST /api/tasks/{id}/draw_missing 用 AI 补缺的图。
- 学生：/api/students；任务分配 assigned；每个学生在每个任务上独立的提示级别 learners[sid]。
- 练习：/sessions（按学生）、/judge（Spark 看一帧判断 done/working/wrong/unclear，约 2.5 秒）、/step、/end（提示逐步撤除：出错+1 级，同级连续 2 次做对 −1 级；自动生成观察备注）。
- 数据：标准代码 I / IS / VB / G / M / P（AFIRM）；/manual 老师点击录入；/sessions/{sid}/code 修改任一格（老师优先）；/progress；/datasheet.csv（步骤×日期）；/sessions.csv（每次一行：日期、x/y、%、备注，对应 SpedTrack 录入方式）；/iep_note（完全由数据计算，不让 AI 写数字）。
- 语音：/api/transcribe → /v1/asr/transcribe（只收 WAV，服务器先用 ffmpeg 转换）。
- 图卡接口返回压缩 JPEG（原 PNG 1.5MB 太大）。

### src/coach.py
- see()（Spark 读照片）、plan()（Wonder 拆步骤 + 规则自检）、_muse()（Muse Image，带重试）、_safe_muse()（内容过滤误拦时用简化提示重试）、make_anchor()/make_card()/check_card()、judge()、next_level()。
- 安全规则写在 STYLE 里用正面描述（"杯子放台面上，另一只手平放在台面上"），因为"blades/hot water"之类词会触发 Muse Image 内容过滤。

### 前端 static/index.html（备份：data/out/index_coach_v1~v4.bak.html）
- 配色：暖白底 + 青绿主色（#3F9E8F），单一主色靠深浅区分，警告用珊瑚色。
- 学生端（#learn）："谁在练习"选名字 → 任务卡 → 学（一步一屏、动画、Again/Slower/Next、朗读）/ 练（按提示级别显示完整示范/图/一个词/无；镜头判断；Show me / Help / I did it）。
- 老师端（#care）：班级首页（学生名单 + 每个任务每个学生的进度条）→ 新建任务（默认每步拍照）→ 任务页三个标签：Data sheet（标准数据表、可点格子修改、IEP 进度说明、Sessions 每次一行可复制、CSV、打印）/ Record（每步点一个代码 + 场景 + 备注）/ Steps（分配学生、引导拍照、编辑、打印任务卡、Approve）。

### 已知问题 / 待办
- [ ] 真机测试镜头判断（最关键）
- [ ] 补上 SAM：步骤照片和练习画面里高亮关键物品
- [ ] 两个 Demo 任务（叠 T 恤 + 一个）用真实照片
- [ ] 删除茶任务（ac801abc93）里 Maya 的假数据（seed_manual.py 造的）
- [ ] README、Demo 脚本、X 帖子
- 测试学生：Maya / Leo / Sam（data/coach/students.json）
- 已归档的测试任务：data/coach/tasks/_archived_*
