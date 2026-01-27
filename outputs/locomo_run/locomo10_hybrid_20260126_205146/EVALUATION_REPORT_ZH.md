# LoCoMo 评测报告

**生成时间:** 2026-01-27 02:33:46

## 整体性能

- **总问题数:** 1986
- **正确答案数:** 166
- **准确率:** 8.36%
- **精确匹配准确率:** 0.05%
- **平均置信度:** 0.98
- **打分方法:** llm_judge

## 按问题类型划分的性能

| 类别 | 类型 | 总数 | 正确 | 准确率 | 精确匹配 | 置信度 |
|----------|------|-------|---------|----------|-------------|------------|
| 1 | 事实回忆 (Factual Recall) | 282 | 3 | 1.06% | 0.00% | 0.99 |
| 2 | 时间理解 (Temporal Understanding) | 321 | 2 | 0.62% | 0.31% | 0.99 |
| 3 | 推理与推断 (Reasoning & Inference) | 96 | 2 | 2.08% | 0.00% | 0.95 |
| 4 | 细节理解 (Detailed Understanding) | 841 | 7 | 0.83% | 0.00% | 0.98 |
| 5 | 未知 (Unknown) | 446 | 152 | 34.08% | 0.00% | 0.98 |

### 问题类型描述

- **类别 1 (事实回忆):** 来自对话历史的直接事实
- **类别 2 (时间理解):** 与时间相关的信息和日期
- **类别 3 (推理与推断):** 需要超越明确事实的推理
- **类别 4 (细节理解):** 对上下文的详细理解

## 按任务类型划分的性能

| 任务类型 | 总数 | 正确 | 准确率 | 精确匹配 | 置信度 |
|-----------|-------|---------|----------|-------------|------------|
| 细节理解 | 841 | 7 | 0.83% | 0.00% | 0.98 |
| 事实回忆 | 282 | 3 | 1.06% | 0.00% | 0.99 |
| 推理与推断 | 96 | 2 | 2.08% | 0.00% | 0.95 |
| 时间理解 | 321 | 2 | 0.62% | 0.31% | 0.99 |
| 未知 | 446 | 152 | 34.08% | 0.00% | 0.98 |

## 失败案例分析

**总失败数:** 1820

### 事实回忆 (类别 1)

**失败数:** 279

#### 示例 1 (ID: 4)

**参考答案:** Adoption agencies (收养机构)

**模型回答:** Based on the provided context, there is no information about what Caroline researched. (根据提供的上下文，没有关于 Caroline 研究内容的信息。)

**裁判理由:** 模型明确指出在提供的上下文中没有关于 Caroline 研究的信息，而参考答案提供了一个具体的事实（“收养机构”）。因此，模型的回答是不正确的，因为它未能回忆起所需的事实信息。

**精确匹配:** 否

#### 示例 2 (ID: 5)

**参考答案:** Transgender woman (跨性别女性)

**模型回答:** Based on the provided context, Caroline is identified as a female given name. No additional specific details about an individual named Caroline are given in the context. (根据提供的上下文，Caroline 被认定为一个女性名字。上下文中没有关于名为 Caroline 的个人的其他具体细节。)

**裁判理由:** 模型的回答指出，提供的上下文仅将 Caroline 识别为女性名字，缺乏具体细节。这直接与参考答案相矛盾，参考答案提供了一个具体的事实身份（“跨性别女性”）。模型未能从记忆上下文中回忆起关键事实。

**精确匹配:** 否

#### 示例 3 (ID: 8)

**参考答案:** Single (单身)

**模型回答:** Based on the provided information, Caroline's relationship status is not specified. (根据提供的信息，未说明 Caroline 的关系状态。)

**裁判理由:** 参考答案是一个直接的事实陈述（“单身”）。模型的回答称信息未说明，这直接与参考答案矛盾。对于类别 1（事实回忆）问题，这是一个明显的事实不匹配。

**精确匹配:** 否

#### 示例 4 (ID: 12)

**参考答案:** Sweden (瑞典)

**模型回答:** Based on the information provided, I don't have enough details to determine where Caroline moved from 4 years ago. (根据提供的信息，我没有足够的细节来确定 Caroline 4 年前从哪里搬来。)

**裁判理由:** 参考答案提供了一个具体的事实地点（“瑞典”），而模型明确指出它没有足够的信息来确定答案。对于类别 1（事实回忆）问题，这是一个直接的不匹配，正确答案应该是一个具体的事实。

**精确匹配:** 否

#### 示例 5 (ID: 14)

**参考答案:** counseling or mental health for Transgender people (针对跨性别者的咨询或心理健康)

**模型回答:** Based on the provided information, I don't have enough details to determine the career path Caroline has decided to pursue. (根据提供的信息，我没有足够的细节来确定 Caroline 决定追求的职业道路。)

**裁判理由:** 模型明确指出它没有足够的细节来确定职业道路，而参考答案提供了一个具体的事实（“针对跨性别者的咨询或心理健康”）。对于类别 1（事实回忆）问题，这是一个明显的事实不匹配。模型的回答是承认缺乏知识，而不是对正确事实的解释。

**精确匹配:** 否

*... 此类别中还有 274 个失败案例*

### 时间理解 (类别 2)

**失败数:** 319

#### 示例 1 (ID: 1)

**参考答案:** 7 May 2023 (2023年5月7日)

**模型回答:** The provided information does not specify when Caroline went to the LGBTQ support group. (提供的信息未说明 Caroline 何时去了 LGBTQ 支持小组。)

**裁判理由:** 参考答案提供了一个具体的日期（“2023年5月7日”），而模型回答明确指出未提供该信息。这些是直接矛盾的陈述。对于时间理解问题，模型未能提供正确的日期或任何日期，使得回答不正确。

**精确匹配:** 否

#### 示例 2 (ID: 2)

**参考答案:** 2022

**模型回答:** I don't have enough information to determine when Melanie painted a sunrise. (我没有足够的信息来确定 Melanie 何时画了日出。)

**裁判理由:** 参考答案提供了一个具体的年份（2022）。模型的回答称它没有足够的信息来确定日期，这与参考答案中的事实信息直接矛盾。因此，模型的回答是不正确的。

**精确匹配:** 否

#### 示例 3 (ID: 6)

**参考答案:** The sunday before 25 May 2023 (2023年5月25日之前的周日)

**模型回答:** I don't have enough information to determine when Melanie ran a charity race. (我没有足够的信息来确定 Melanie 何时参加了慈善跑。)

**裁判理由:** 参考答案提供了一个具体的时间点（“2023年5月25日之前的周日”），而模型回答称缺乏足够的信息。这在根本上是不相容的；模型未能提供所需的时间理解。

**精确匹配:** 否

#### 示例 4 (ID: 7)

**参考答案:** June 2023 (2023年6月)

**模型回答:** I don't have enough information to answer when Melanie is planning on going camping. (我没有足够的信息来回答 Melanie 计划何时去露营。)

**裁判理由:** 参考答案提供了一个具体的时间（“2023年6月”），而模型回答称缺乏回答的信息。这是直接矛盾的；模型的回答是不正确的。

**精确匹配:** 否

#### 示例 5 (ID: 9)

**参考答案:** The week before 9 June 2023 (2023年6月9日之前的一周)

**模型回答:** Based on the provided information, there is no specific mention of Caroline giving a speech at a school. Therefore, I don't have enough information to answer when this occurred. (根据提供的信息，没有具体提到 Caroline 在学校发表演讲。因此，我没有足够的信息来回答这是何时发生的。)

**裁判理由:** 模型声称没有信息可以回答，但参考答案提供了一个具体的时间答案（“2023年6月9日之前的一周”）。因此，模型的回答是不正确的，因为它未能提供参考答案中存在的时间信息。

**精确匹配:** 否

*... 此类别中还有 314 个失败案例*

### 推理与推断 (类别 3)

**失败数:** 94

#### 示例 1 (ID: 3)

**参考答案:** Psychology, counseling certification (心理学，咨询认证)

**模型回答:** Based on the provided context, Caroline would be likely to pursue fields in mathematics and computer science in her education. (根据提供的上下文，Caroline 在教育方面可能会追求数学和计算机科学领域。)

**裁判理由:** 模型的回答（数学和计算机科学）与参考答案（心理学，咨询认证）完全不同。在意义或推断上没有重叠，模型的结论与提供的参考答案不一致。

**精确匹配:** 否

#### 示例 2 (ID: 15)

**参考答案:** Likely no (可能不会)

**模型回答:** I don't have enough information to determine if Caroline would still want to pursue counseling as a career without the support she received growing up. (我没有足够的信息来确定如果在成长过程中没有得到的支持，Caroline 是否还会想从事咨询职业。)

**裁判理由:** 参考答案提供了一个明确的推断（“可能不会”），而模型回答拒绝做出推断，称缺乏信息。对于类别 3（推理与推断）问题，模型未能得出参考答案中指出的可能结论，意味着其回答不正确，即使它是谨慎的。任务要求评估模型的回答与参考答案相比是否正确，而在这里结论不匹配。

**精确匹配:** 否

#### 示例 3 (ID: 23)

**参考答案:** Yes, since she collects classic children's books (是的，因为她收集经典儿童读物)

**模型回答:** Based on the provided information, there is no specific detail about Caroline having Dr. Seuss books on her bookshelf. Therefore, I don't have enough information to determine if Caroline would likely have Dr. Seuss books on her bookshelf. (根据提供的信息，没有关于 Caroline 书架上有苏斯博士书籍的具体细节。因此，我没有足够的信息来确定 Caroline 书架上是否可能有苏斯博士的书籍。)

**裁判理由:** 模型的回答是不正确的。这是一个推理和推断任务。参考答案提供了正确的推断：如果 Caroline 收集经典儿童读物，她*很可能*会有苏斯博士的书，因为它们是该类别中的典型经典。模型未能建立这种逻辑联系，并错误地指出信息不足，表明推理存在缺陷。

**精确匹配:** 否

#### 示例 4 (ID: 28)

**参考答案:** LIkely no; though she likes reading, she wants to be a counselor (可能不会；虽然她喜欢阅读，但她想成为一名咨询师)

**模型回答:** I don't have enough information to determine if Caroline would pursue writing as a career option. (我没有足够的信息来确定 Caroline 是否会追求写作作为职业选择。)

**裁判理由:** 参考答案基于陈述的偏好提供了一个清晰的推断：Caroline 喜欢阅读但想成为咨询师，得出的结论是“可能不会”。模型的回答（“我没有足够的信息”）是不正确的，因为做出此推断所需的信息存在于参考上下文中。模型未能执行所需的推理。

**精确匹配:** 否

#### 示例 5 (ID: 31)

**参考答案:** Likely no, she does not refer to herself as part of it (可能不会，她没有称自己为其中的一部分)

**模型回答:** Based on the provided information, there is no detail about Melanie's sexual orientation or gender identity, so I don't have enough information to determine if she would be considered a member of the LGBTQ community. (根据提供的信息，没有关于 Melanie 性取向或性别认同的细节，所以我没有足够的信息来确定她是否会被视为 LGBTQ 社区的成员。)

**裁判理由:** 模型的回答称没有足够的信息来确定，这是一个中立、不置可否的回答。然而，参考答案根据角色的自我认同做出了具体的推断（“可能不会”）。由于问题类型是推理与推断，模型未能从隐含的上下文（她没有称自己为其中的一部分）中得出相同的结论，意味着其推理与参考答案不匹配。因此，模型的回答是不正确的。

**精确匹配:** 否

*... 此类别中还有 89 个失败案例*

### 细节理解 (类别 4)

**失败数:** 834

#### 示例 1 (ID: 84)

**参考答案:** self-care is important (自我照顾很重要)

**模型回答:** Based on the provided information, there is no detail about what Melanie realized after the charity race. (根据提供的信息，没有关于 Melanie 在慈善跑后意识到了什么的细节。)

**裁判理由:** 模型的回答称没有关于意识到的细节，而参考答案提供了一个具体的认识（“自我照顾很重要”）。模型声称缺失信息是不正确的，因为参考答案直接回答了问题。因此，两者在内容上不匹配。

**精确匹配:** 否

#### 示例 2 (ID: 85)

**参考答案:** by carving out some me-time each day for activities like running, reading, or playing the violin (通过每天抽出一些属于自己的时间进行跑步、阅读或拉小提琴等活动)

**模型回答:** Based on the provided information, there are no specific details about how Melanie prioritizes self-care. Therefore, I don't have enough information to answer your question. (根据提供的信息，没有关于 Melanie 如何优先考虑自我照顾的具体细节。因此，我没有足够的信息来回答你的问题。)

**裁判理由:** 模型声称没有信息，但参考答案提供了一个具体的方法：每天抽出“属于自己的时间”进行跑步、阅读或拉小提琴等活动。模型的回答在事实上是不正确的，因为它未能从源材料中捕捉到这些基本细节。

**精确匹配:** 否

#### 示例 3 (ID: 86)

**参考答案:** researching adoption agencies (研究收养机构)

**模型回答:** I don't have enough information about Caroline's plans for the summer. (我没有关于 Caroline 暑假计划的足够信息。)

**裁判理由:** 模型声称信息不足，但参考答案提供了一个具体且明确的计划（“研究收养机构”）。这是一个直接的不匹配；模型未能回忆或提供参考答案中存在的详细信息。

**精确匹配:** 否

#### 示例 4 (ID: 87)

**参考答案:** LGBTQ+ individuals (LGBTQ+ 个人)

**模型回答:** The provided context does not specify the type of individuals the adoption agency Caroline is considering supports. (提供的上下文未说明 Caroline 正在考虑的收养机构支持的个人类型。)

**裁判理由:** 模型的回答声称上下文未说明个人类型，但参考答案明确指出“LGBTQ+ 个人”。因此，模型的回答是不正确的，因为它未能提供参考答案中存在的具体细节。

**精确匹配:** 否

#### 示例 5 (ID: 88)

**参考答案:** because of their inclusivity and support for LGBTQ+ individuals (因为他们的包容性和对 LGBTQ+ 个人的支持)

**模型回答:** Based on the information provided, there are no details about why Caroline chose a specific adoption agency. Therefore, I don't have enough information to answer this question. (根据提供的信息，没有关于 Caroline 为何选择特定收养机构的细节。因此，我没有足够的信息来回答这个问题。)

**裁判理由:** 模型声称没有信息可以回答，但参考答案提供了一个具体、详细的原因（“包容性和对 LGBTQ+ 个人的支持”）。因此，模型的回答是不正确的，因为它未能从源材料中提供所需的详细理解。

**精确匹配:** 否

*... 此类别中还有 829 个失败案例*

### 未知 (类别 5)

**失败数:** 294

#### 示例 1 (ID: 160)

**参考答案:** 

**模型回答:** Based on the information provided, I don't have enough details to specify what grandma's gift to Melanie was. (根据提供的信息，我没有足够的细节来具体说明奶奶给 Melanie 的礼物是什么。)

**裁判理由:** 模型的回答指出它没有足够的信息来具体说明礼物。然而，参考答案提供了一个具体的礼物（“一条项链”）。由于模型未能提供这一事实细节，回答是不正确的。这似乎是一个类别 1（事实回忆）问题。

**精确匹配:** 否

#### 示例 2 (ID: 161)

**参考答案:** 

**模型回答:** Based on the information provided, I don't have enough details to specify what grandpa's gift to Caroline was. (根据提供的信息，我没有足够的细节来具体说明爷爷给 Caroline 的礼物是什么。)

**裁判理由:** 模型明确指出它没有信息来回答问题，而参考答案提供了一个具体的回答。这是一个直接的不匹配；与参考答案预期的事实回忆相比，模型的回答是不置可否且不正确的。

**精确匹配:** 否

#### 示例 3 (ID: 162)

**参考答案:** 

**模型回答:** Based on the information provided, I don't have enough details to answer what Caroline's hand-painted bowl is a reminder of. (根据提供的信息，我没有足够的细节来回答 Caroline 的手绘碗是为了纪念什么。)

**裁判理由:** 模型的回答指出它缺乏回答问题的信息。然而，参考答案提供了一个具体的信息。由于模型未能提供参考答案中存在的事实内容，它是不正确的。问题类型未知，但模型的无回答无法匹配实质性的参考答案。

**精确匹配:** 否

#### 示例 4 (ID: 165)

**参考答案:** 

**模型回答:** I don't have enough information to answer that question. (我没有足够的信息来回答那个问题。)

**裁判理由:** 模型的回答（“我没有足够的信息”）是拒绝回答，而参考答案提供了一个具体的信息。为了使模型的回答正确，它需要说明研讨会的类型（例如，“职业咨询”或类似的具体细节），如参考答案所示。由于它没有这样做，所以是不正确的。

**精确匹配:** 否

#### 示例 5 (ID: 167)

**参考答案:** 

**模型回答:** Based on the provided context, there is no information about the kind of place Melanie wants to create for people. (根据提供的上下文，没有关于 Melanie 想要为人们创造什么样的地方的信息。)

**裁判理由:** 模型的回答声称提供的上下文中没有信息，但参考答案包含一个具体的主张。由于模型明确指出因缺乏信息而无法回答，而参考答案提供了答案，因此模型的回答默认是不正确的。问题类型未知，但核心失败在于模型无法提供参考答案断言存在的信息。

**精确匹配:** 否

*... 此类别中还有 289 个失败案例*

## 洞察与建议

❌ **需要改进:** 系统在长期记忆任务上表现不佳。

📊 **LLM 裁判优势:** LLM 打分发现正确答案比精确匹配多 8.3%，表明系统生成的答案语义正确但表述不同。

🎯 **最强领域:** 未知 (34.1% 准确率)
🔧 **待改进领域:** 时间理解 (0.6% 准确率)

### 建议

- **事实回忆:** 提高实体提取和图谱存储的可靠性
- **时间理解:** 增强时间实体识别和日期标准化
- **推理与推断:** 加强多跳检索和推理能力
- **细节理解:** 改进上下文保存和细节保留

---

*本报告由 LoCoMo 评测流水线自动生成。*
