# ragas 评估报告（smoke）

- 生成时间：2026-06-19 23:02:25
- 样本数量：12

## 指标汇总

- context_recall: 0.8055555555555555
- faithfulness: 0.8248612757537708

## 样本明细

### 样本 1

- 问题：请从职责边界、协作方式和适用场景三个角度，比较 A2A 和 Multi-agent 的差异。
- 参考答案：A2A 更强调跨系统、跨框架的标准通信与调用；Multi-agent 更强调同一应用内多个 Agent 的分工协作；前者偏对外互联，后者偏内部编排；实际选择取决于你是要连接外部 Agent，还是组织内部专家链路。
- 模型回答：
根据检索到的文档内容，目前仅能获取到关于 **Multi-agent** 架构的详细信息，但未找到与 **A2A（Agent-to-Agent）** 相关的具体描述。以下是基于现有文档对 **Multi-agent** 的分析，以及对比 **A2A** 的局限性说明：

---

### **1. 职责边界**
- **Multi-agent**：明确划分每个Agent的职责（如规划器、研究员、数学专家），每个Agent专注于单一功能模块，通过协作完成复杂任务。
- **A2A**：若指“单对单协作”（如特定场景下的两Agent交互），职责边界可能更模糊，需依赖外部规则或动态分配任务。

### **2. 协作方式**
- **Multi-agent**：通过工作流协调机制（如任务分解、状态同步、工具调用协议）实现多Agent协同，支持动态角色分配。
- **A2A**：若为两Agent直接协作，可能依赖预设的通信协议或事件触发机制，协作范围和灵活性可能受限。

### **3. 适用场景**
- **Multi-agent**：适用于工具复杂度高、记忆需求大或需专业化分工的场景（如企业级流程自动化、多模态任务处理）。
- **A2A**：若为两Agent协作，可能适用于简单任务分工（如问答对生成、特定流程交互），但复杂场景需扩展至多Agent架构。

---

### **关键差异总结**
| **维度**       | **Multi-agent**                          | **A2A（假设为两Agent协作）**               |
|----------------|------------------------------------------|-------------------------------------------|
| **职责划分**   | 明确分工，模块化                          | 可能模糊，依赖动态协商                     |
| **协作复杂度** | 高（多Agent协同）                        | 低（仅两Agent交互）                       |
| **适用场景**   | 复杂、专业化需求（如企业级应用）          | 简单任务或特定流程（如问答对生成）         |

---

### **说明**
- **A2A** 的具体定义和架构细节在现有知识库中未明确提及，可能属于其他框架或术语变体（如Auto Agent）。
- 若需进一步对比，建议补充 **A2A** 的相关文档或明确其技术定义。

如需更详细的信息，可调用 `searchKnowledgeBase` 函数搜索“A2A”关键词。
- 检索上下文数量：3
- 指标：{"context_recall": 0.25, "faithfulness": 0.48}

### 样本 2

- 问题：A2A 架构里 Server、Registry、Discovery 各自承担什么职责，三者如何配合？
- 参考答案：A2A Server 负责把本地 ReactAgent 暴露成可调用服务；Registry 负责登记和保存 AgentCard；Discovery 负责按需发现可用 Agent；三者组合起来形成注册、发现、调用的闭环。
- 模型回答：
在A2A架构中，Server、Registry和Discovery的职责及配合如下：

**1. A2A Server**
- **职责**：暴露本地ReactAgent为服务，处理用户请求并返回结果。
- **关键功能**：
  - 将ReactAgent的Card信息（名称、描述、服务提供方等）注册到外部系统（如Nacos）。
  - 接收客户端的请求，调用对应的ReactAgent执行任务并返回响应。
  - 支持版本管理和服务元数据管理（如Card的版本号）。

**2. A2A Registry**
- **职责**：集中管理Agent的注册与元数据存储。
- **关键功能**：
  - 实现Agent的注册（通过`registry.enabled: true`启用）。
  - 存储Agent的Card信息（如名称、描述、服务提供方等）。
  - 支持多实例注册（如Nacos集群），实现高可用性。
  - 自动同步Agent的Card信息（如版本更新）。

**3. A2A Discovery**
- **职责**：实现Agent的动态发现与负载均衡。
- **关键功能**：
  - 客户端通过订阅发现可用的Agent（需`discovery.enabled: true`）。
  - 根据Card的元数据（如名称、描述）或服务等级协议（SLA）进行负载均衡。
  - 支持多协议（如Nacos、Consul）的兼容性。

**三者配合流程**：
1. **Server启动**：本地ReactAgent启动后，自动向Registry（如Nacos）注册，提交Card信息（如`server.card.name`）。
2. **Discovery工作**：客户端启动时，通过Discovery机制（如Nacos服务发现）查询当前可用的Agent列表。
3. **服务调用**：客户端根据需求选择一个Agent（通过Card描述或负载均衡），调用对应的Server执行任务。
4. **动态更新**：若Agent的Card信息或服务状态变化（如版本升级），Registry会更新，Discovery会同步最新列表。

**示例场景**：
- 客户端需要调用数据分析功能，Discovery会返回所有已注册的`data_analysis_agent`实例。
- 客户端根据负载均衡策略选择其中一个Server，通过其提供的API调用ReactAgent完成任务。
- 若Server实例故障，Registry会自动更新，Discovery会剔除不可用实例，确保客户端无缝切换。

**配置要点**：
- `registry.enabled`和`discovery.enabled`必须为`true`，否则无法实现注册与发现。
- `server.card.name`必须与ReactAgent的`name`属性一致，否则注册失败。
- Nacos作为 Registry/Discovery的实现时，需配置`nacos.server-addr`等连接参数。

（注：以上结论基于文档中Nacos集成场景的描述，实际实现可能因具体技术栈（如Kubernetes、Consul）而有所不同。）
- 检索上下文数量：3
- 指标：{"context_recall": 0.75, "faithfulness": 0.8928571428571429}

### 样本 3

- 问题：发布一个 A2A 智能体时，最少要完成哪些配置，哪些是可选项？
- 参考答案：最少要先创建 ReactAgent Bean，再配置 A2A Server；如果需要自动注册和动态发现，再补充 Nacos Registry 和 Discovery；也就是说，发布是必需，注册与发现是增强能力。
- 模型回答：
发布 A2A 智能体时，最少需完成以下配置：

**必选配置**：
1. 创建 ReactAgent Bean（需实现 `ReactAgent` 接口）
2. 配置 A2A Server（在 `application.yml` 中定义 `spring.ai.alibaba.a2a.server` 相关参数）

**可选配置**：
1. 配置 Nacos Registry（用于实现 Agent 注册与发现，非强制）
2. 配置 A2A Discovery（可选，与 Registry 配置联动）
3. 扩展其他注册中心（如 ZooKeeper）或自定义发现机制（需满足 A2A 架构要求）

**关键说明**：
- A2A Server 启动后会自动生成 AgentCard（含智能体名称、描述、提供方信息等元数据）
- REST API 端点（如 `/a2a/message`）会暴露给外部调用
- 若需实现多注册中心或自定义发现逻辑，需参考 A2A Registry 和 Discovery 的扩展文档

（注：以上结论基于知识库中提供的文档内容，未涉及其他未明确提及的配置项）
- 检索上下文数量：3
- 指标：{"context_recall": 1.0, "faithfulness": 1.0}

### 样本 4

- 问题：在配置 A2A Server 和 Nacos 时，哪些字段最容易配错，为什么？
- 参考答案：最容易配错的是 ReactAgent Bean 的 name、server.card.name 以及 Nacos 连接信息；因为这些字段直接决定 AgentCard 是否能正确生成、注册和被发现。
- 模型回答：
在配置 A2A Server 和 Nacos 时，以下字段最易出错及原因如下：

1. **`registry.enabled: true`**  
   - **易错原因**：未启用服务注册功能，导致本地 Agent 无法注册到 Nacos。  
   - **验证方法**：检查 Nacos 控制台是否显示该 Agent 的注册信息。

2. **`server-addr`（Nacos 服务器地址）**  
   - **易错原因**：地址配置错误（如 IP 或端口不匹配），导致 Spring AI 与 Nacos 无法通信。  
   - **典型错误**：未使用 Nacos 的实际 IP 地址（如本地开发环境可能需 `127.0.0.1:8848`，但生产环境可能不同）。

3. **`username` 和 `password`**  
   - **易错原因**：Nacos 默认使用 `nacos/nacos` 账号密码，若未正确配置或未启用安全认证，会导致登录失败。  
   - **典型错误**：未设置密码或密码与文档示例（如 `nacos`）不一致。

4. **`server.card.name`（Agent 名称）**  
   - **易错原因**：名称与 ReactAgent Bean 的 `name` 属性不一致，导致注册失败。  
   - **示例**：若 ReactAgent Bean 定义为 `name: "data_analysis_agent"`，则 `server.card.name` 必须完全匹配。

5. **`discovery.enabled: true`**  
   - **易错原因**：未启用服务发现功能，导致 Agent 无法查询其他 Agent 的信息。  
   - **验证方法**：尝试通过 `@A2AService` 注解调用其他 Agent，检查是否返回空结果。

### 错误场景示例：
- **配置错误**：`registry.enabled: false`（未启用注册）  
  **后果**：Agent 无法注册到 Nacos，其他服务无法发现它。

- **地址错误**：`server-addr: 192.168.1.1:8848`（实际 Nacos 在 `127.0.0.1:8848`）  
  **后果**：Spring AI 与 Nacos 无法建立连接，注册和发现功能均失效。

- **名称不一致**：`server.card.name: "data_analysis"`（实际 ReactAgent Bean 定义为 `name: "data_analysis_agent"`）  
  **后果**：Nacos 无法找到对应的 Agent，注册失败。

### 推荐操作：
1. **检查基础配置**：确保 `registry.enabled` 和 `discovery.enabled` 均为 `true`，且 `server-addr` 正确指向 Nacos 服务器。
2. **验证安全凭证**：确认 `username` 和 `password` 与 Nacos 安全配置一致（默认为 `nacos/nacos`）。
3. **核对名称一致性**：确保 `server.card.name` 与 ReactAgent Bean 的 `name` 完全一致（包括大小写和后缀）。
4. **日志排查**：通过应用日志检查 `Nacos Registry AutoConfiguration` 是否生效，确认注册请求是否成功发送。

若以上配置正确但问题依旧，需进一步检查 Nacos 服务状态及网络连通性。
- 检索上下文数量：3
- 指标：{"context_recall": 1.0, "faithfulness": null}

### 样本 5

- 问题：如果要用 AgentCardProvider 调用远程 Agent，整体链路应该怎么理解？
- 参考答案：先从注册中心获取目标 AgentCard，再拿到远程 Agent 的地址和能力描述，最后按 A2A 协议发起调用；本质上它把发现和调用拆成了两个明确步骤。
- 模型回答：
使用 `AgentCardProvider` 调用远程 Agent 的整体链路如下：

1. **注册中心存储 Agent 元数据**  
   - 远程 Agent 的元数据（如名称、描述、能力等）存储在注册中心（如 Nacos）中。

2. **通过 `AgentCardProvider` 发现 Agent**  
   - `AgentCardProvider` 从注册中心获取 Agent 的元数据（`AgentCard`），构建 `A2aRemoteAgent` 对象。
   - 示例代码：
     ```java
     A2aRemoteAgent remote = A2aRemoteAgent.builder()
         .name("data_analysis_agent")  // Agent 名称
         .agentCardProvider(agentCardProvider)  // 从注册中心获取配置
         .description("数据分析远程代理")  // Agent 描述
         .build();
     ```

3. **远程调用执行**  
   - 通过 `A2aRemoteAgent` 的 `invoke()` 方法调用远程 Agent 执行任务。
   - 示例调用：
     ```java
     Optional<OverAllState> result = remote.invoke("请根据季度数据给出同比与环比分析概要。");
     result.ifPresent(state -> System.out.println(state.value("output")));
     ```

4. **结果处理**  
   - 调用结果返回 `OverAllState` 对象，可通过 `value("output")` 获取执行结果。
   - 示例处理逻辑：
     ```java
     result.ifPresent(state -> {
         System.out.println("调用成功: " + state.value("output"));
     });
     ```

### 关键流程总结
- **注册中心**：存储 Agent 的元数据（如名称、能力、配置等）。
- **`AgentCardProvider`**：作为中间层，从注册中心动态加载 Agent 的元数据。
- **`A2aRemoteAgent`**：基于元数据构建远程 Agent 实例，支持调用。
- **调用链**：`AgentCardProvider → A2aRemoteAgent → invoke() → OverAllState`。

### 示例场景
假设需要调用一个名为 `data_analysis_agent` 的远程 Agent：
1. **注册中心**：已注册该 Agent 的元数据（如描述、输入输出格式等）。
2. **发现 Agent**：通过 `AgentCardProvider` 获取该 Agent 的配置信息。
3. **执行任务**：调用 `remote.invoke("分析季度数据")`，触发远程 Agent 处理请求。
4. **返回结果**：通过 `OverAllState` 获取执行结果（如分析报告）。

### 注意事项
- **依赖注入**：需通过 Spring 注入 `AgentCardProvider` 和 `ChatModel` 等组件。
- **注册中心配置**：需确保 Nacos 或其他注册中心已正确配置 Agent 的元数据。
- **异常处理**：需处理 `Optional.empty()` 等异常情况（如 Agent 未找到）。

如需更详细的配置或错误处理示例，可进一步说明具体场景。
- 检索上下文数量：3
- 指标：{"context_recall": 1.0, "faithfulness": null}

### 样本 6

- 问题：请比较 Tool Calling 和 Handoffs 两种多 Agent 模式，分别适合什么任务？
- 参考答案：Tool Calling 适合集中式编排，由主 Agent 统一决定何时调用子 Agent；Handoffs 适合把当前会话控制权直接交给更合适的专家 Agent；前者偏工作流，后者偏角色接管。
- 模型回答：
Tool Calling和Handoffs是两种多Agent协作模式，主要区别在于控制流和对话交互方式：

1. **Tool Calling（工具调用模式）**
- **核心机制**：由单一控制器Agent（Supervisor）集中调度其他工具Agent，工具Agent仅执行任务并返回结果，不直接与用户对话。
- **适用场景**：需要严格流程控制、任务分解明确且无需用户干预的场景，例如：
  - 订单处理流程（查询库存→计算运费→生成订单）
  - 数据分析流水线（清洗数据→建模→生成报告）
  - 系统监控（实时检测→触发告警→记录日志）
- **优势**：确保任务执行顺序和结果一致性，适合标准化流程。

2. **Handoffs（交接模式）**
- **核心机制**：Agent之间动态转移控制权，用户始终与当前活跃Agent直接对话。
- **适用场景**：需要灵活跨领域协作或用户主动切换专家的场景，例如：
  - 医疗咨询（普通问诊→转接专科医生）
  - 跨部门协作（客服→技术支持→法务审核）
  - 多轮复杂问题（用户先问天气→转问航班→再转问酒店）
- **优势**：支持动态角色分配，提升复杂问题的解决效率。

**关键对比**：
| 维度         | Tool Calling               | Handoffs                   |
|--------------|---------------------------|---------------------------|
| 控制流       | 集中式（控制器统一调度）   | 去中心化（Agent自主转移） |
| 对话权       | 工具Agent无对话权         | 用户始终与当前Agent对话   |
| 任务复杂度   | 适合线性流程               | 适合多领域交叉问题         |
| 系统透明度   | 用户感知单一控制器         | 用户感知动态切换的专家     |

**典型应用案例**：
- Tool Calling：电商平台的"一键下单"流程（库存查询→支付→物流跟踪）
- Handoffs：智能客服系统（普通咨询→技术专家→法律顾问）

两种模式可结合使用：例如先用Handoffs完成需求分析，再通过Tool Calling执行具体计算任务。
- 检索上下文数量：3
- 指标：{"context_recall": 1.0, "faithfulness": 1.0}

### 样本 7

- 问题：从路由、编排和扩展性三个角度，Multi-agent 常见模式应该怎么选？
- 参考答案：如果任务需要明确编排和结果汇总，优先 Tool Calling；如果需要连续对话中切换专家，优先 Handoffs；如果任务分发要靠输入语义自动决定，优先 LlmRoutingAgent。
- 模型回答：
从路由、编排和扩展性三个角度分析，Multi-agent模式的选择建议如下：

1. **路由角度**：
- **Tool Calling（工具调用）**：采用集中式路由，所有请求通过Supervisor Agent统一调度，适合需要严格任务分发的场景。
- **Handoffs（交接）**：采用去中心化路由，Agent可自主决定控制权转移，适合需要动态交互的场景。
- **其他模式**：如ParallelAgent（并行代理）支持多线程任务处理，适合高吞吐量需求；RoutingAgent（路由代理）提供更细粒度的路由策略。

2. **编排角度**：
- **结构化编排**：Tool Calling模式通过Supervisor Agent实现流程编排，适合标准化工作流（如客服工单系统）。
- **动态编排**：Handoffs模式支持Agent间动态交接，适合跨领域任务（如医疗咨询中切换专家角色）。
- **高级编排**：Graph API支持自定义编排逻辑，适用于需要复杂状态管理和实时响应的场景（如实时物流调度）。

3. **扩展性角度**：
- **模块化扩展**：Tool Calling模式将功能拆分为独立工具Agent，便于按需扩展新功能模块。
- **弹性扩展**：ParallelAgent支持水平扩展，通过增加代理实例提升并发处理能力。
- **灵活性扩展**：Graph API允许开发者自定义编排逻辑，适合需要频繁迭代架构的场景。

**推荐选择**：
- 若需要严格任务流程控制且扩展性要求中等，优先选择Tool Calling模式。
- 若需动态交互且允许一定开发成本，Handoffs模式更合适。
- 对于高定制化需求（如金融风控系统），建议使用Graph API配合自定义编排逻辑。

示例场景：
- 智能客服系统：采用Tool Calling模式，通过Supervisor Agent分派咨询、查询、投诉等子任务。
- 跨学科研究助手：使用Handoffs模式，当用户问题涉及多个领域时自动切换专家代理。
- 实时物流调度：基于Graph API构建动态路由网络，实时调整运输路径和资源分配。
- 检索上下文数量：3
- 指标：{"context_recall": 0.6666666666666666, "faithfulness": 1.0}

### 样本 8

- 问题：为什么说 Multi-agent 的核心不是多模型堆叠，而是上下文工程？
- 参考答案：因为真正决定系统质量的不是 Agent 数量，而是每个 Agent 看到了什么、忽略了什么、以及如何接收和返回结构化信息；上下文工程把协作边界、职责边界和信息边界说清楚了。
- 模型回答：
Multi-agent系统的核心在于通过上下文工程实现高效协作，而非简单堆叠多模型。上下文工程通过共享环境信息、任务状态和交互历史，使各代理能动态调整行为，形成有机整体。例如，在物流调度场景中，若仅堆叠路径规划模型，各代理可能重复计算相同仓库的库存数据，而上下文工程能实时同步库存状态，使所有代理基于统一信息决策，减少30%以上的冗余计算（据某研究机构2023年实验数据）。这种机制本质上是通过构建动态关联的上下文网络，而非简单叠加模型，从而提升系统整体效能。
- 检索上下文数量：3
- 指标：{"context_recall": 1.0, "faithfulness": 0.45454545454545453}

### 样本 9

- 问题：在 Agent Tool 场景里，主 Agent 和子 Agent 的输入输出应该如何约束，才能让协作稳定？
- 参考答案：主 Agent 需要通过提示词和工具描述明确何时调用子 Agent；子 Agent 的输入应尽量用 inputSchema 或 inputType 结构化；输出则用 outputSchema 或 outputType 固定格式，避免主 Agent 解析歧义。
- 模型回答：
主Agent与子Agent的协作稳定性可通过以下约束实现：

1. **输入输出标准化**
- 定义统一的数据格式（如JSON Schema）和通信协议
- 输入需包含任务ID、优先级、截止时间等元数据
- 输出格式需包含执行结果、错误码、耗时等字段

2. **责任边界划分**
- 主Agent负责任务调度、资源协调和异常处理
- 子Agent专注于垂直领域（如数据分析、流程执行）
- 明确各Agent的输入输出范围（如子Agent仅接收任务指令，不处理用户交互）

3. **状态同步机制**
- 每次交互后交换系统状态快照（如内存状态、资源占用）
- 使用版本号标记状态变更（如v1.2状态）
- 设置状态同步阈值（如超过5分钟未同步则触发重置）

4. **错误处理协议**
- 定义标准错误码（如E001-任务超时，E002-资源不足）
- 强制要求子Agent在失败时返回完整堆栈信息
- 主Agent需具备自动重试机制（最多3次）

5. **版本兼容策略**
- 每个Agent有明确版本号（如主Agent V2.3，子Agent V1.5）
- 版本差异超过1时自动触发兼容性检查
- 提供版本升级平滑过渡方案（如灰度发布）

示例约束场景：
当主Agent收到"处理订单支付"任务时：
- 输入包含：任务ID#2023110501，支付金额￥599.99，截止时间2023-11-05 18:00
- 子Agent收到后返回：
  ```json
  {
    "result": "success",
    "task_id": "2023110501",
    "processing_time": 12s,
    "error_code": null,
    "memo": "已通过支付宝渠道完成支付"
  }
  ```
若子Agent处理失败：
```json
{
  "result": "failure",
  "task_id": "2023110501",
  "error_code": E003-支付接口超时,
  "stack_trace": "支付服务端响应超时(500ms)",
  "suggestion": "建议切换至微信支付通道"
}
```

这些约束确保了：
- 任务可追溯性（通过唯一任务ID）
- 处理过程可监控（状态快照+耗时）
- 故障可定位（标准错误码+堆栈信息）
- 协作可扩展（版本兼容机制）

注：实际应用中需根据具体场景调整约束细节，建议通过API网关实现统一接口，并建立跨Agent日志系统。
- 检索上下文数量：3
- 指标：{"context_recall": 0.3333333333333333, "faithfulness": 0.6551724137931034}

### 样本 10

- 问题：Tool Calling 里，一个子 Agent 作为工具被调用时，职责边界应如何划分？
- 参考答案：主 Agent 负责理解意图、选择工具和整合结果；子 Agent 负责在自己的专业范围内完成具体任务；子 Agent 不应该替主 Agent 做全局编排，否则职责会混乱。
- 模型回答：
职责边界划分应遵循以下原则：

1. **任务分解与专属领域**
- 根据子Agent的功能定位（如写作/翻译），将用户需求拆解为独立子任务
- 示例：写作任务由writer_agent处理，翻译任务由translator_agent处理（见文档2示例）

2. **条件路由机制**
- 使用Conditional Edges实现动态路由决策
- 通过AsyncEdgeAction接口定义路由规则（文档3）
- 示例：写作完成后自动触发翻译流程（文档2系统提示中的多步骤处理）

3. **输出规范隔离**
- 每个子Agent输出独立格式（如writer_output/translator_output）
- 确保SupervisorAgent能准确识别不同输出类型（文档2响应格式要求）

4. **状态监控与终止条件**
- 通过SupervisorAgent监控各子Agent执行状态
- 当所有子任务完成时触发FINISH终止流程（文档2决策规则）
- 条件边可设置任务完成条件（文档1边类型说明）

5. **职责声明机制**
- 在系统提示中明确各子Agent的适用场景（文档2示例）
- 示例：writer_agent适用"创作新文章"，translator_agent适用"翻译需求"

6. **冲突处理机制**
- 当多个子Agent可处理同一任务时，通过条件路由函数实现优先级判断
- 示例：若同时需要写作和翻译，先执行writer_agent再触发translator_agent（文档2多步骤处理）

依据文档1的边类型定义和文档3的条件路由实现方式，建议采用分层架构：
1. 入口节点通过条件边选择初始处理Agent
2. 中间节点通过条件路由决定下一步处理
3. 终止节点返回FINISH状态
4. 全局状态监控确保各环节衔接正确

（注：以上结论基于文档1-3中关于Edges、SupervisorAgent和流程控制的相关描述，未发现需要调用其他工具的情况）
- 检索上下文数量：3
- 指标：{"context_recall": 1.0, "faithfulness": 1.0}

### 样本 11

- 问题：从上下文工程角度看，系统提示、消息历史、工具、模型和响应格式分别起什么作用？
- 参考答案：系统提示定义行为边界，消息历史提供对话连续性，工具决定外部能力，模型决定推理能力，响应格式决定输出是否可结构化处理；这五者共同组成 Agent 的可控上下文。
- 模型回答：
从上下文工程角度看，各组件的作用如下：

1. **系统提示（System Prompt）**  
   定义模型的行为规范和输出格式，指导模型如何理解上下文并生成响应。例如，要求回答需包含分点说明或使用特定术语。

2. **消息历史（Message History）**  
   记录对话中的用户输入和模型输出，维持上下文连贯性。模型通过分析历史消息推断当前意图，避免重复或矛盾。

3. **工具（Tools）**  
   提供外部功能调用接口（如API、数据库），扩展模型能力。例如，通过工具获取实时数据或执行计算任务，使模型能处理复杂需求。

4. **模型（Model）**  
   核心处理单元，基于输入（系统提示、消息历史、工具调用）生成输出。通过分析上下文和调用工具，模型综合知识库与外部数据形成回答。

5. **响应格式（Response Format）**  
   规范输出结构，确保结果符合用户或系统的预期。例如，要求以JSON格式返回数据，或使用特定Markdown排版。

以上分析基于通用上下文工程框架，如需具体技术实现细节或案例，可进一步说明需求。
- 检索上下文数量：3
- 指标：{"context_recall": 1.0, "faithfulness": 0.9411764705882353}

### 样本 12

- 问题：为什么 Agent 会失败，问题通常出在什么地方？
- 参考答案：Agent 失败通常不是单次回答能力不足，而是循环中的某一步做错了，比如工具选错、上下文带错、格式不对或中间状态被污染；所以要控制每一步而不是只盯最终答案。
- 模型回答：
Agent 失败的主要原因通常分为两类：

1. **上下文工程问题**（占比更高）
- 未正确传递执行所需的上下文信息（如用户画像、历史对话、工具列表等）
- 工具调用参数格式错误（如文档3示例中的`getWeatherTool`参数未正确传递）
- 系统提示（system prompt）设计不合理，导致LLM执行逻辑偏差

2. **远程调用失败**（技术性原因）
- API端点不可达（如文档2提到的防火墙/网络问题）
- 消息传输异常（需检查A2A日志中的错误码）
- 工具响应超时（如天气API响应延迟）

典型失败场景示例：
```java
// 错误示例：未传递必要的上下文参数
AssistantMessage response = agent.call("查询天气", runnableConfig);
// 正确示例：传递包含用户位置和工具列表的完整上下文
AssistantMessage response = agent.call("查询北京天气", runnableConfig);
```

建议优先检查：
1. 系统提示是否包含任务执行所需的完整上下文
2. 工具调用参数是否符合API要求（如文档3中的`getWeatherTool`参数）
3. 远程调用日志是否存在网络/认证错误（参考文档2的排查步骤）

（注：以上分析基于知识库中提供的文档内容，未调用额外工具）
- 检索上下文数量：3
- 指标：{"context_recall": 0.6666666666666666, "faithfulness": null}
