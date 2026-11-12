# -*- coding: utf-8 -*-
"""毕业设计初稿 → 智能旅行规划系统：整体改写入口"""
import os, sys, zipfile, shutil, copy
from lxml import etree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docutil import *

SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
OUT = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\out_pass1.docx"
WORK = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\_unz"
DIAG = r"c:\Users\decade\Desktop\TravelAgent\diagrams"
SHOT = r"c:\Users\decade\AppData\Local\Temp\shots"

import pprint as _pp

def qn(nm):
    return q(nm)

# ---------- 1. 解压 ----------
if os.path.exists(WORK):
    shutil.rmtree(WORK)
os.makedirs(WORK)
with zipfile.ZipFile(SRC) as z:
    z.extractall(WORK)

DOC = os.path.join(WORK, "word", "document.xml")
parser = etree.XMLParser(remove_blank_text=False)
root = etree.parse(DOC, parser).getroot()
body = root.find(qn("body"))

# ---------- 2. clean_red (必须先于所有其它操作) ----------
clean_red(root)
for h in ["header1.xml", "header2.xml", "header3.xml"]:
    hp = os.path.join(WORK, "word", h)
    if os.path.exists(hp):
        clean_red(etree.parse(hp, parser).getroot())

paras = [c for c in body if c.tag == qn("p")]
tbls  = [c for c in body if c.tag == qn("tbl")]
P = lambda i: paras[i]

# helper
def idx(body, paras):
    return {id(p): i for i, p in enumerate(paras)}

# 需要实时获取元素引用，因为 clean_red / 后续操作会改 body 顺序。
# 但我们以初始 paras 快照索引为锚，插入删除用 body.insert/remove。

def ins_after(ref_para, new_el):
    body.insert(list(body).index(ref_para) + 1, new_el)

def ins_before(ref_para, new_el):
    body.insert(list(body).index(ref_para), new_el)

# ---------- 3. 正文文字定义 ----------
# 摘要
ABS = ("针对传统旅行规划依赖人工攻略、信息零散、难以结合用户偏好与实时条件做动态调整的问题，"
       "本文设计并实现一套基于 FastAPI 和 Vue3 的交互式旅行规划智能体系统。系统采用前后端分离架构，"
       "后端以 FastAPI 提供异步接口，前端使用 Vue3 配合 TypeScript 与 Pinia 构建页面；核心规划能力由"
       "LangGraph 状态图编排，并结合函数调用与检索增强生成技术完成需求解析、行程组织与结果反思，"
       "通过 SSE 服务端推送实现分步流式输出。系统划分用户、AI 规划、工具调用与知识库等模块，"
       "提供行程生成、行程编辑、行程分享与评论、个人中心等功能，管理员可进行内容审核与运行监控。"
       "数据库采用 MySQL 存储业务数据，借助 Redis 实现限流、幂等与会话缓存，并引入乐观锁与事务保障一致性；"
       "通过向量检索与相似度阈值过滤提升回答准确率，降低事实性错误。测试结果表明系统响应迅速、"
       "规划结果准确，能够根据目的地、天数与偏好自动生成较合理的行程，满足实际使用需求。")
ABSKEY = "FastAPI；Vue3；智能体；行程规划；LangGraph；RAG；SSE"

ABSTRACT = ("Traditional travel planning often relies on manually compiled guides, while the "
            "information is scattered and difficult to combine personal preferences with real-time "
            "conditions for dynamic adjustment. This paper designs and implements an interactive "
            "travel planning agent system based on FastAPI and Vue3. The system adopts a "
            "front-end and back-end separation architecture. The back end provides asynchronous "
            "interfaces with FastAPI, and the front end is built with Vue3, TypeScript and Pinia. "
            "The core planning capability is orchestrated by a LangGraph state machine, combined "
            "with function calling and retrieval-augmented generation to complete requirement "
            "parsing, itinerary organization and result reflection, and realizes step-by-step "
            "streaming output through SSE. The system is divided into user, AI planning, tool "
            "invocation and knowledge base modules, providing itinerary generation, editing, "
            "sharing and comments, personal center and other functions, while administrators can "
            "conduct content review and operation monitoring. MySQL stores business data, and "
            "Redis implements rate limiting, idempotency and session caching, while optimistic "
            "locking and transactions guarantee consistency. Vector retrieval and similarity "
            "threshold filtering improve the answer accuracy and reduce factual errors. Test "
            "results show that the system responds quickly and produces reasonable itineraries "
            "according to destination, days and preferences, meeting practical requirements.")
ABSTRACTKEY = "FastAPI; Vue3; Agent; Travel Planning; LangGraph; RAG; SSE"

EN_TITLE = "The Design and Implementation of Intelligent Travel Planning System Based on FastAPI and Vue3"

# 1.1 背景
BG1 = "随着生活水平提高和节假日增多，自助旅行逐渐成为主流出行方式，但多数游客在制订行程时仍依赖搜索引擎、游记与社交平台，需要反复查阅大量信息才能拼凑出可行方案，效率低、体验差。许多在线旅行产品虽然提供了酒店、交通与景点预订，却缺少能够结合用户时间、预算与兴趣自动编排行程的能力。"
BG2 = "与此同时，大语言模型在自然语言理解、知识问答与工具调用方面表现出较强能力，为智能化的行程规划提供了新思路。将大模型与检索增强生成、实时工具调用相结合，可以让系统在理解用户模糊需求的基础上，主动联网查询天气、景点与位置信息，最终生成结构化的行程安排。"
BG3 = "基于上述背景，本文设计并实现一套基于 FastAPI 和 Vue3 的交互式旅行规划智能体系统，利用 LangGraph 状态图编排多阶段规划流程，结合函数调用与知识库检索生成贴近用户需求的行程，并通过流式输出即时反馈，探索大模型技术在垂直场景中的落地方式。"

# 1.2.1 国内
CNNOW = "国内在大模型与智能问答应用方面的研究进展迅速。朱宇豪等人面向铁路出行场景，研究了行程规划与推荐服务的智能体构建方法，将需求理解、资源检索与结果生成进行整合，为出行领域的智能体设计提供了参考。江志英等提出基于思维代码的大语言模型多工具协调调用提示方法，通过显式的思维结构引导模型在多工具环境下合理拆解任务，改善工具调用的一致性与成功率。车万翔等对模型时代自然语言处理面临的挑战与发展方向进行了系统性梳理，指出工具使用、规划与多轮交互是重要研究议题。在工程实践层面，国内 Web 系统普遍采用前后端分离架构，结合 RAG 技术搭建知识库问答，应用日益广泛。"
# 1.2.2 国外
FNNOW = "国外对推理与工具使用的研究起步较早。Yao 等提出 ReAct 范式，将推理轨迹与行动交错执行，使模型在推理的同时调用工具并依据反馈调整，显著提升了在问答与决策任务上的表现。Lewis 等提出检索增强生成框架，通过引入外部知识缓解了知识密集型自然语言处理任务中模型幻觉与知识过时的问题。Schick 等提出 Toolformer，使模型能够学习自行调用外部工具，拓展了模型的能力边界。Xie 等构建了面向真实世界规划的 TravelPlanner 基准，考察语言智能体在多约束条件下的规划能力。Xu 等提出 ReWOO，将推理与观测解耦，减少了冗余的模型调用。这些工作共同为交互式行程规划智能体的实现奠定了理论基础。"

# 1.3 意义
# 1.4 六条
S14 = [
    "调研真实旅行规划场景，梳理游客与管理员的业务流程，明确行程规划、编辑、分享等核心功能需求；",
    "选用 FastAPI+Vue3+LangGraph+RAG 技术栈，搭建前后端分离架构，通过 SSE 实现流式输出；",
    "完成系统功能模块划分，绘制功能结构图、业务流程图与数据库 E-R 图；",
    "设计用户、行程、行程日、行程项、分享动态等核心业务数据表；",
    "实现游客浏览、用户行程生成与编辑、行程分享评论，以及管理员审核与监控等全部功能；",
    "编写功能测试用例并完成系统测试，修复 Bug 保证系统稳定运行。",
]

# 第2章
FUN_LEAD = "需求分析是项目开发的基础，只有厘清游客、普通用户与管理员三方的真实诉求，才能避免后期大量返工。本系统按照游客、普通用户、管理员三类角色划分权限，普通用户与管理员的功能相互隔离。"
FN_REQ = "根据对智能旅行规划系统的分析研究，本系统设计了不同的角色，包括游客、普通用户和管理员。游客可浏览系统首页与公开行程，但无生成与管理权限；普通用户在登录后可以使用行程生成、编辑、分享、评论等主要功能；管理员则负责内容审核、用户管理与运行监控。"
FUN_ROLE = [
    "游客：浏览系统首页、公开行程与知识库内容，不支持行程生成与编辑；",
    "普通用户：注册、登录、修改个人信息；输入目的地、天数与偏好生成行程；对行程进行编辑、分享与删除；浏览他人行程并评论、点赞；个人中心管理我的行程与动态；",
    "管理员：审核待审核的行程分享动态（通过/驳回）；管理用户账号与禁用状态；查看 LLM 调用、工具调用与系统运行统计。",
]
NORM_ANAL = "普通用户模块分析：普通用户需要登录账号，使用该账号输入出发地、目的地、出发日期、天数与偏好标签，点击生成后系统按步骤解析需求、查询景点与天气、整合知识库资料，最终返回按天分组的行程。行程生成后用户可以逐日查看，编辑其中的景点与时间，并将行程以分享动态的形式发布到社区，供他人浏览评论。该模块涉及行程生成、行程管理、行程分享与个人中心等若干子功能。"
# 2.2
PERF = [
    "页面响应：正常网络下所有接口响应在 3 秒以内，首页与行程列表数据加载在 1 秒以内；",
    "并发支持：同时支持较多用户在线浏览与生成行程，无明显卡顿与接口超时；",
    "流式输出：行程生成的中间步骤通过 SSE 分步推送，避免长时间空白等待。",
]
SECU = [
    "密码加密：用户密码通过加盐哈希加密存储，数据库不保存明文；",
    "登录鉴权：后端使用 JWT 校验身份，未登录用户禁止访问行程生成等受保护接口；",
    "角色权限：普通用户无法直接访问管理员后台接口，越权请求直接拦截；",
    "内容管控：管理员对分享动态进行审核，违规内容不对外展示。",
]
COMPAT = [
    "浏览器：适配 Chrome、Edge、360 等主流 PC 浏览器；",
    "分辨率：适配 1366、1920 等标准电脑屏幕，页面布局不产生错乱；",
    "后端：可在 Windows、Linux 环境部署运行，支持 Docker 一键编排。",
]

# 第3章
M1 = "本系统的整体设计分前端与后端两个方面：前端负责页面展示与交互，采用 Vue3、TypeScript 与 Pinia，包含首页、行程生成、行程列表、个人中心、分享社区与后台管理等页面；后端使用 FastAPI 提供异步接口，核心规划流程由 LangGraph 状态图编排，通过函数调用完成天气、景点等实时查询，并结合知识库检索补全信息，使用 SSE 向前端流式推送进度。整体功能模块划分如图3.1所示。"
M2 = "根据功能模块的划分，可以得到系统的总体流程。系统主界面如图4.1所示。整体上，游客与普通用户从首页入口进入，普通用户登录后由用户模块进入行程规划页面，系统解析需求并调用相关工具后生成行程，随后用户可编辑、分享行程；管理员从后台入口登录，进行内容审核、用户管理与运行监控，系统总流程如图3.2所示。"
# 3.2.1
ER1 = "概念模型设计用于描述现实世界中实体及其联系。根据对旅行规划业务的分析，本系统的核心实体包括用户、行程、行程日、行程项、分享动态、知识库文档等。一个用户可以生成多个行程，一个行程包含多个行程日，一个行程日又包含多个行程项；用户可发布多条分享动态，每条动态对应一个行程。实体之间通过这些一对一或一对多的联系相互关联。"
ER2 = "由实体及其联系可以得到系统整体 E-R 图，如图3.3所示。"
# 3.2.2
DBLEAD = "根据系统总体设计可以确定本项目的核心业务表包括用户表、行程表、行程日表、行程项表、分享动态表等。各表之间通过主外键关联，具体结构见下表所示。"
# 表头
COLHEAD = ["序号", "字段名", "说明", "类型"]

# 表3.1 用户表
T31_TITLE = "表3.1 用户表"
T31_ROWS = [
    ["1", "id", "用户编号，主键自增", "BIGINT"],
    ["2", "username", "用户名，唯一", "VARCHAR(50)"],
    ["3", "password", "密码哈希值", "VARCHAR(255)"],
    ["4", "nickname", "昵称", "VARCHAR(50)"],
    ["5", "avatar", "头像地址", "VARCHAR(255)"],
    ["6", "created_at", "创建时间", "DATETIME"],
]
# 表3.2 行程表
T32_TITLE = "表3.2 行程表"
T32_ROWS = [
    ["1", "id", "行程编号，主键自增", "BIGINT"],
    ["2", "user_id", "所属用户，外键", "BIGINT"],
    ["3", "city", "目的地城市", "VARCHAR(50)"],
    ["4", "start_date", "出发日期", "DATE"],
    ["5", "days", "行程天数", "INT"],
    ["6", "status", "行程状态", "TINYINT"],
]
# 表3.3 行程日表
T33_TITLE = "表3.3 行程日表"
T33_ROWS = [
    ["1", "id", "行程日编号，主键自增", "BIGINT"],
    ["2", "trip_id", "所属行程，外键", "BIGINT"],
    ["3", "day_index", "第几天", "INT"],
    ["4", "date", "日期", "DATE"],
    ["5", "summary", "当日行程概述", "VARCHAR(1000)"],
    ["6", "created_at", "创建时间", "DATETIME"],
]
# 表3.4 行程项表
T34_TITLE = "表3.4 行程项表"
T34_ROWS = [
    ["1", "id", "行程项编号，主键自增", "BIGINT"],
    ["2", "day_id", "所属行程日，外键", "BIGINT"],
    ["3", "start_time", "开始时间", "VARCHAR(20)"],
    ["4", "title", "项目名称", "VARCHAR(200)"],
    ["5", "place", "地点", "VARCHAR(200)"],
    ["6", "note", "备注", "VARCHAR(500)"],
]
# 表3.5 分享动态表
T35_TITLE = "表3.5 分享动态表"
T35_ROWS = [
    ["1", "id", "动态编号，主键自增", "BIGINT"],
    ["2", "trip_id", "关联行程，外键", "BIGINT"],
    ["3", "user_id", "发布用户，外键", "BIGINT"],
    ["4", "visibility", "可见范围", "TINYINT"],
    ["5", "likes", "点赞数", "INT"],
    ["6", "created_at", "创建时间", "DATETIME"],
]

# 第4章
C41 = "系统主界面采用清新简洁的旅行风格，顶部为全局导航栏，包含首页、行程规划、分享社区、个人中心与登录入口；中间区域展示推荐目的地与快捷入口。对于未登录的游客，仅展示公开内容，点击登录后进入个人首页。系统主页面如图4.1所示，行程列表展示用户已生成的行程记录，支持继续编辑与删除。"
C42_login = "在进入系统后，用户可以点击右上角登录。登录接口使用 FastAPI 异步处理：后端按用户名查询用户，校验密码哈希，校验通过后签发 JWT，并将令牌写入 Redis 会话缓存，返回给前端存储。核心登录代码如下："
CODE_LINES = [
    '@router.post("/auth/login", response_model=TokenOut)',
    'async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):',
    '    stmt = select(User).where(User.username == data.username)',
    '    user = await db.scalar(stmt)',
    '    if user is None:',
    '        raise HTTPException(status_code=401, detail="账号或密码错误")',
    '    if not verify_password(data.password, user.password):',
    '        raise HTTPException(status_code=401, detail="账号或密码错误")',
    '    token = create_access_token(subject=str(user.id), expires=7200)',
    '    await redis.setex(f"token:{user.id}", 7200, token)',
    '    return TokenOut(token=token, nickname=user.nickname)',
]
C42_gen = "行程生成是系统的核心功能。用户在表单中输入目的地、出发日期、天数和偏好标签后点击生成，系统随即进入规划流程：先是解析需求，填充默认值；接着通过函数调用查询景点与天气，从知识库检索相关资料；然后整理并按天组织行程；最后对结果进行反思校验，通过 SSE 将上述步骤分步推送到前端，形成步骤条动画。生成的行程可逐日展开查看，如图4.2所示。"
C42_share = "行程生成后可进行分享。用户点击分享，选择可见范围（公开、仅互关好友、仅自己）后发布为动态，其他用户可浏览、评论与点赞。详情页面展示行程的每日安排、天气建议与应用的工具，支持复制分享链接，如图4.3所示。"
# 4.3
C43 = "管理员登录后台后可对平台进行管理。后台采用侧边栏导航，包含内容审核、用户管理和运行监控等页面。"
C431 = "首页的动态通过审核后才会公开。管理员在内容审核页面可查看待审核分享动态，选择通过或驳回，驳回需填写理由；审核通过的动态在社区中按可见范围展示，如图4.4所示。"
C432 = "工具调用监控页面展示 LLM 调用、工具调用的次数与耗时，数据统计页面通过图表呈现各城市行程数量、接口响应时间等指标，帮助管理员了解系统运行情况，如图4.5所示。"

# 第5章
T5_1 = "系统开发完成后仍可能存在逻辑漏洞、交互异常、权限越权等潜在问题，通过黑盒功能测试遍历核心模块，验证各项需求功能是否正常执行，修复发现的 Bug，确保上线后用户使用稳定、规划结果准确。"
T5_2 = "本次测试主要针对行程生成这一核心模块开展，重点验证需求解析、工具调用、流式输出与保存等关键流程。"
T5_21_TITLE = "5.2.1 行程生成模块的测试"
TEST_LEAD = "在行程生成模块的功能测试中，需验证行程生成的完整流程。用户使用正确的账号密码登录系统后，点击“行程规划”进入表单页面，填写城市、出发日期、天数和偏好标签后点击生成，观察步骤条是否依次出现，核对生成的行程是否按天组织、时间顺序是否正确。测试用例如表 5.1 所示。"
TBL51_TITLE = "表5.1 行程生成用例测试表"
T5_3_1 = "本次共设计若干条功能测试用例，覆盖登录注册、行程生成、行程编辑、行程分享、评论点赞与后台管理等核心功能，主要功能通过率较高。系统登录鉴权、流式输出、行程保存等核心流程均验证通过。"
T5_3_2 = "测试中发现少量页面排版、步骤提示小问题，已全部修复；系统响应速度与规划准确度满足需求，整体功能完整，达到毕业设计预期目标，可投入实际使用。"

# 结论
CONC_LEAD = "本课题围绕自助旅行规划效率低、信息分散的痛点，完成基于 FastAPI 和 Vue3 的交互式旅行规划智能体系统的设计与开发。整体工作总结如下："
CONC_ITEMS = [
    "完成需求调研，划分游客、普通用户、管理员三类角色，梳理行程规划等核心业务模块，明确性能、安全、兼容三类非功能需求；",
    "搭建成熟技术栈：FastAPI 异步后端、Vue3+TypeScript 前端、LangGraph 状态图编排、RAG 知识库、MySQL 与 Redis，实现前后端分离架构；",
    "完成系统概要设计与详细设计，绘制功能结构图、业务流程图与 E-R 图，设计五张核心业务数据表并遵循第三范式；",
    "实现游客浏览、行程生成与编辑、行程分享评论及后台审核监控等全部功能，给出核心业务代码与系统界面截图；",
    "开展黑盒功能测试，验证系统功能稳定，修复测试 Bug，系统满足实际使用需求。",
]
CONC_END = "本系统弥补了传统人工规划依赖攻略、信息分散的短板，将大模型、检索增强生成与工具调用技术引入行程规划场景，形成需求解析、工具查询、知识增强、结果反思的完整闭环，轻量易部署，适合实际应用。项目开发过程巩固了 Python、FastAPI、前端工程与大模型应用等多项技能，也为后续进一步扩展多智能体协同规划打下基础。"

# 致谢
THX1 = "本次毕业设计《基于 FastAPI 和 Vue3 的交互式旅行规划智能体的设计与实现》是在指导老师全程悉心指导下完成的。从选题、文献查阅、需求分析，到框架搭建、代码开发与论文修改，老师提出了许多宝贵意见，在此向我的指导老师致以诚挚的感谢。"
THX2 = "在校学习期间，各位任课老师传授了 Python、前端、数据库与软件工程等专业基础知识，为本次项目开发打下了扎实的理论基础；同学在开发遇到报错、格式调整时互相交流探讨，提供了很多实用思路。"
THX3 = "在此，向我的指导老师、所有授课教师与身边同学致以真诚谢意。毕业设计是对大学学习的总结，今后我会继续钻研软件开发与大模型应用技术，不断提升自身的专业能力。致谢人：成晓宇，2026年5月。"

# 参考文献
REFS = [
    "[1] 朱宇豪, 戴琳琳, 景辉, 等. 面向铁路出行的行程规划与推荐服务智能体研究[J]. 铁路计算机应用, 2026, 35(5): 30-35.",
    "[2] 江志英, 黄震. 基于思维代码的大语言模型多工具协调调用提示方法[J]. 北京化工大学学报(自然科学版), 2025, 52(3): 105-113.",
    "[3] Yao S, Zhao J, Yu D, et al. ReAct: Synergizing Reasoning and Acting in Language Models[C]//ICLR. 2023.",
    "[4] Lewis P, Perez E, Piktus A, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks[C]//NeurIPS 33. 2020: 9459-9474.",
    "[5] Schick T, Dwivedi-Yu J, Dessì R, et al. Toolformer: Language Models Can Teach Themselves to Use Tools[C]//NeurIPS 36. 2023.",
    "[6] Xie J, Zhang K, Chen J, et al. TravelPlanner: A Benchmark for Real-World Planning with Language Agents[J]. arXiv:2402.01622, 2024.",
    "[7] Xu S, Pang S, Jiang M, et al. ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models[J]. arXiv:2305.18323, 2023.",
    "[8] 车万翔, 窦志成, 冯岩松, 等. 大模型时代的自然语言处理：挑战、机遇与发展[J]. 中国科学:信息科学, 2023, 53(9): 1645-1687.",
    "[9] 王珊, 萨师煊. 数据库系统概论(第5版)[M]. 北京: 高等教育出版社, 2014.",
    "[10] Fielding R T. Architectural Styles and the Design of Network-based Software Architectures[D]. Irvine: University of California, Irvine, 2000.",
]

# ---------- 4. 正文改写 ----------
# 摘要区
set_two(P(74), None, "课题名称")
# P74 原只有单 run"课题名称"。set_two 需 2 个 text run。改用 set_para。
set_para(P(74), "课题名称：基于FastAPI和Vue3的交互式旅行规划系统")
set_two(P(75), "摘要：", ABS)
set_two(P(76), "关键词：", ABSKEY)
# P79 英文题目
set_para(P(79), EN_TITLE, keep_br=True)
set_two(P(80), "Abstract: ", ABSTRACT)
set_two(P(81), "Keywords: ", ABSTRACTKEY)

# 第1章
set_heading(P(102), "第1章 绪论")            # P101 sectPr，不加分页
set_heading(P(103), "1.1 系统开发背景")
set_para(P(104), BG1)
# P105 已有正文模板可复用
set_para(P(105), BG2)
# P106 是红注释? probe37 未列。P106 idx.txt 是格式说明(红)。clean_red 已删红文本，可能只剩空 run。P106 原为格式说明段。
set_para(P(106), BG3)
set_heading(P(107), "1.2 国内外研究现状")
set_heading(P(108), "1.2.1 国内研究现状")
set_para(P(109), CNNOW)
set_heading(P(110), "1.2.2 国外研究现状")
# P111 空文本框 pict 需删除，正文保留。detach pict run (rId in textbox无图) —— 删 pict run。
# P111 有 r0 正文 + r1 textbox pict。detach pict 并仅保留正文。
pic = detach_pict(P(111))
if pic is not None:
    pic.getparent().remove(pic) if pic.getparent() is not None else None
set_para(P(111), FNNOW)
set_heading(P(113), "1.3 系统的研究意义")
set_para(P(114), "（1）实践意义")
set_para(P(115), "从用户角度看，系统将繁琐的人工规划转化为自动化的智能生成，缩短了决策时间，提高了行程的合理性与可执行性。")
set_para(P(116), "从技术角度看，系统将大模型、RAG 与实时工具调用相结合，探索了智能体在垂直场景中的工程化落地，具有一定参考价值。")
set_para(P(117), "（2）学习意义")
set_para(P(118), "通过本系统开发，完整掌握了 FastAPI 异步后端、Vue3 前端工程化、LangGraph 状态图编排、RAG 知识库、MySQL 与 Redis 等主流技术，提升了前后端分离开发与大模型应用的实战能力。")
set_heading(P(120), "1.4 系统研究的主要内容")
for i, txt in enumerate(S14):
    set_para(P(121 + i), "  " + txt)

# 第2章
set_heading(P(127), "第2章 系统分析", page_break=False)
# P127 已带"(另起一页)"红 run 被删除，且 P127 有 page? idx.txt 显示 P127 前有'(另起一页)'。P127 有 br。保留原 br。
add_page_break_before(P(127))
set_heading(P(129), "2.1 系统功能分析")
set_para(P(130), FUN_LEAD)
set_heading(P(132), "2.1.1 功能需求")
set_para(P(133), FN_REQ)
set_para(P(134), "1、面向普通用户的功能需求。")
for i, txt in enumerate(FUN_ROLE):
    set_para(P(135 + i), "  " + txt)
set_heading(P(138), "2.1.2 普通用户模块分析")
set_para(P(139), NORM_ANAL)
# P140 caption 保留"图2.1 用户用例图"
# 新增 2.1.3 管理员用户模块分析（插入 P139 之后，P141 之前）—— P140 caption 之后
# P138/P139 captions: P139 正文, P140 图2.1 caption, P141 红注释(删)
set_para(P(140), "图2.1 普通用户用例图")
set_heading(P(142), "2.2 系统非功能性分析")
set_heading(P(143), "2.2.1 性能需求")
for i, txt in enumerate(PERF):
    set_para(P(144 + i), "\uf0b7  " + txt)
set_heading(P(147), "2.2.2 安全性需求")
for i, txt in enumerate(SECU):
    set_para(P(148 + i), "\uf0b7  " + txt)
set_heading(P(152), "2.2.3 兼容性需求")
for i, txt in enumerate(COMPAT):
    set_para(P(153 + i), "\uf0b7  " + txt)
# P155 末尾含'第3章 系统设计'，只保留 r0 正文，删除其他 run(含 br r1)。P155 正文=兼容性第三条
set_para(P(155), "\uf0b7  " + COMPAT[2], keep_br=False)

# 第3章（标题独立新建于 P155 后）
CH3_tmpl = copy.deepcopy(P(102))
set_heading(CH3_tmpl, "第3章 系统设计", page_break=True)
ins_after(P(155), CH3_tmpl)

# 重新定位 paras（删除/插入后索引变化）→ 用引用法重建
paras = [c for c in body if c.tag == qn("p")]
tbls = [c for c in body if c.tag == qn("tbl")]

def getp(tag_key, start=0):
    """按文本定位段落引用"""
    for p in body:
        if p.tag != qn("p"):
            continue
        t = "".join(x for x in p.itertext())
        if tag_key in t:
            return p
    return None

set_heading(getp("3.1 系统功能模块设计"), "3.1 系统功能模块设计")
M1P = getp("本系统的设计分为前端和后端两个方面")
set_para(M1P, M1)
# 图3.1 caption (P159)
set_para(getp("图3.1 总体功能模块图"), "图3.1 系统功能模块图")
# P160 正文（含图3.2）
set_para(getp("根据普通用户的功能模块总结"), M2)
set_para(getp("图3.2 游客和普通用户功能模块图"), "图3.2 系统业务流程图")
set_heading(getp("3.2 系统数据库设计"), "3.2 系统数据库设计")
set_heading(getp("3.2.1 据库概念模型设计"), "3.2.1 数据库概念模型设计")
set_para(getp("本项目采用数据库概论模型设计"), ER1)
set_para(getp("实体图可以得出系统整体E-R图"), ER2)
set_para(getp("图3.3 系统E-R图"), "图3.3 系统E-R图")
set_heading(getp("3.2.2 数据库表设计"), "3.2.2 数据库表设计")
set_para(getp("根据系统总体设计可以确定本项目的基本表"), DBLEAD)
# 删除 P169 描述段（避免与题注重复，DBLEAD 已涵盖说明文字）
p169 = getp("（1）用户信息表：id是主键")
if p169 is not None:
    body.remove(p169)

# ---------- 5. 表格填充 ----------
# 题注段按“表X.X …”宽松匹配，取其后紧跟的 tbl
def captions():
    caps = []
    for c in body:
        if c.tag != qn("p"):
            continue
        txt = "".join(c.itertext()).strip()
        if txt.startswith("表3") or txt.startswith("表5"):
            caps.append(c)
    return caps

def tbl_after_caption(cap_p):
    cur = cap_p.getnext()
    while cur is not None and cur.tag != qn("tbl"):
        cur = cur.getnext()
    return cur

caps = captions()
table_caps = [c for c in caps if "".join(c.itertext()).strip().startswith("表3")]
TBL0 = tbl_after_caption(table_caps[0]) if len(table_caps) > 0 else None
TBL1 = tbl_after_caption(table_caps[1]) if len(table_caps) > 1 else None
print("TBL0", TBL0 is not None, "TBL1", TBL1 is not None, "ncap", len(table_caps))

def fill_std(tbl, rows):
    """rows 不含表头，表头=COLHEAD"""
    data = [COLHEAD] + rows
    fill_table(tbl, data)

if TBL0 is not None:
    fill_std(TBL0, T31_ROWS)
if TBL1 is not None:
    fill_std(TBL1, T32_ROWS)

# 新增 表3.3~3.5（克隆 TBL0，置于 TBL1 之后）
TBL2 = copy.deepcopy(TBL0)
fill_std(TBL2, T33_ROWS)
TBL3 = copy.deepcopy(TBL0)
fill_std(TBL3, T34_ROWS)
TBL4 = copy.deepcopy(TBL0)
fill_std(TBL4, T35_ROWS)

# 题注段（克隆 P169 题注样式）
cap_tmpl = getp("表3.1 用户信息表")
def add_caption_then_table(after_el, cap_text, tbl_el):
    cap = copy.deepcopy(after_el)
    set_para(cap, cap_text)
    # 题注插在 after_el 后，表格插在题注后
    body.insert(list(body).index(after_el) + 1, cap)
    body.insert(list(body).index(cap) + 1, tbl_el)

anchor = TBL1
add_caption_then_table(anchor, "表3.3 行程日表", TBL2)
add_caption_then_table(TBL2, "表3.4 行程项表", TBL3)
add_caption_then_table(TBL3, "表3.5 分享动态表", TBL4)

# ---------- 6. 图片调整 ----------
# 需在删除段落前处理。重新定位图段 pict。
def pict_paras():
    res = {}
    for p in body:
        if p.tag != qn("p"):
            continue
        for sh in p.iter("{%s}imagedata" % V):
            rid = sh.get(q("id", R) if False else "{%s}id" % R)
            res.setdefault(p, []).append(rid)
    return res

# 图片尺寸（pt）
def img_size(px_w, px_h):
    wpt = px_w * 0.75
    hpt = px_h * 0.75
    s = min(420 / wpt, 470 / hpt, 1.0)
    return wpt * s, hpt * s

SIZES = {
    "image2": img_size(372, 470),   # 01 用例图
    "image3": img_size(420, 131),   # 02 功能模块图 → 420x131px? 需要按实际
    "image4": img_size(292, 470),   # 03 业务流程图
    "image5": img_size(420, 292),   # 04 E-R 图
}
SHOT_SIZE = img_size(420, 262)

# 由于图段定位复杂且 body 已变动，本步放在后续专门函数（pict_handling）执行。
# 此处仅打印诊断，实际图片处理在下方单独实现。

# ---------- 存档占位 ----------
# 图片处理与段落删除在 rewrite2 段进行，此处先将 document 写回
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(DOC, "wb") as f:
    f.write(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))

# 重新打包
if os.path.exists(OUT):
    os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for folder, _, files in os.walk(WORK):
        for fn in files:
            fp = os.path.join(folder, fn)
            arc = os.path.relpath(fp, WORK)
            z.write(fp, arc)

# 统计
out_root = etree.parse(os.path.join(WORK, "word", "document.xml"), parser).getroot()
ob = out_root.find(qn("body"))
opar = [c for c in ob if c.tag == qn("p")]
otbl = [c for c in ob if c.tag == qn("tbl")]
print("PARAS", len(opar), "TABLES", len(otbl))
print("DONE partial ->", OUT)
