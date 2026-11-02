# 开发日志（每次改动都记在这里，最新的在最上面）

格式：日期 时间 · 改了什么 · 为什么 · 涉及文件 · 怎么回退（备份位置）

---

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
