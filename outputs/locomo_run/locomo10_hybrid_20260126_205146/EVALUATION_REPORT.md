# LoCoMo Evaluation Report

**Generated:** 2026-01-27 02:33:46

## Overall Performance

- **Total Questions:** 1986
- **Correct Answers:** 166
- **Accuracy:** 8.36%
- **Exact Match Accuracy:** 0.05%
- **Average Confidence:** 0.98
- **Scoring Method:** llm_judge

## Performance by Question Type

| Category | Type | Total | Correct | Accuracy | Exact Match | Confidence |
|----------|------|-------|---------|----------|-------------|------------|
| 1 | Factual Recall | 282 | 3 | 1.06% | 0.00% | 0.99 |
| 2 | Temporal Understanding | 321 | 2 | 0.62% | 0.31% | 0.99 |
| 3 | Reasoning & Inference | 96 | 2 | 2.08% | 0.00% | 0.95 |
| 4 | Detailed Understanding | 841 | 7 | 0.83% | 0.00% | 0.98 |
| 5 | Unknown | 446 | 152 | 34.08% | 0.00% | 0.98 |

### Question Type Descriptions

- **Category 1 (Factual Recall):** Direct facts from conversation history
- **Category 2 (Temporal Understanding):** Time-related information and dates
- **Category 3 (Reasoning & Inference):** Requires reasoning beyond explicit facts
- **Category 4 (Detailed Understanding):** Detailed comprehension of context

## Performance by Task Type

| Task Type | Total | Correct | Accuracy | Exact Match | Confidence |
|-----------|-------|---------|----------|-------------|------------|
| Detailed Understanding | 841 | 7 | 0.83% | 0.00% | 0.98 |
| Factual Recall | 282 | 3 | 1.06% | 0.00% | 0.99 |
| Reasoning & Inference | 96 | 2 | 2.08% | 0.00% | 0.95 |
| Temporal Understanding | 321 | 2 | 0.62% | 0.31% | 0.99 |
| unknown | 446 | 152 | 34.08% | 0.00% | 0.98 |

## Failure Analysis

**Total Failures:** 1820

### Factual Recall (Category 1)

**Failures:** 279

#### Example 1 (ID: 4)

**Reference:** Adoption agencies

**Model Answer:** Based on the provided context, there is no information about what Caroline researched.

**Judge Reasoning:** The model explicitly states there is no information about Caroline's research in the provided context, while the reference answer provides a specific fact ('Adoption agencies'). Therefore, the model's answer is incorrect as it fails to recall the required factual information.

**Exact Match:** No

#### Example 2 (ID: 5)

**Reference:** Transgender woman

**Model Answer:** Based on the provided context, Caroline is identified as a female given name. No additional specific details about an individual named Caroline are given in the context.

**Judge Reasoning:** The model's answer states that the provided context only identifies Caroline as a female given name and lacks specific details. This directly contradicts the reference answer, which provides a specific factual identity ('Transgender woman'). The model has failed to recall the key fact from the memory context.

**Exact Match:** No

#### Example 3 (ID: 8)

**Reference:** Single

**Model Answer:** Based on the provided information, Caroline's relationship status is not specified.

**Judge Reasoning:** The reference answer is a direct factual statement ('Single'). The model's answer states the information is not specified, which directly contradicts the reference. This is a clear factual mismatch for a Category 1 (Factual Recall) question.

**Exact Match:** No

#### Example 4 (ID: 12)

**Reference:** Sweden

**Model Answer:** Based on the information provided, I don't have enough details to determine where Caroline moved from 4 years ago.

**Judge Reasoning:** The reference answer provides a specific factual location ('Sweden'), while the model explicitly states it does not have enough information to determine the answer. This is a direct mismatch for a Category 1 (Factual Recall) question where the correct answer is a concrete fact.

**Exact Match:** No

#### Example 5 (ID: 14)

**Reference:** counseling or mental health for Transgender people

**Model Answer:** Based on the provided information, I don't have enough details to determine the career path Caroline has decided to pursue.

**Judge Reasoning:** The model explicitly states it does not have enough details to determine the career path, while the reference answer provides a specific fact ('counseling or mental health for Transgender people'). This is a clear factual mismatch for a Category 1 (Factual Recall) question. The model's answer is an admission of lack of knowledge, not a paraphrased version of the correct fact.

**Exact Match:** No

*... and 274 more failures in this category*

### Temporal Understanding (Category 2)

**Failures:** 319

#### Example 1 (ID: 1)

**Reference:** 7 May 2023

**Model Answer:** The provided information does not specify when Caroline went to the LGBTQ support group.

**Judge Reasoning:** The reference answer provides a specific date ('7 May 2023'), while the model answer explicitly states the information is not provided. These are directly contradictory statements. For a Temporal Understanding question, the model's failure to provide the correct date, or any date, makes the answer incorrect.

**Exact Match:** No

#### Example 2 (ID: 2)

**Reference:** 2022

**Model Answer:** I don't have enough information to determine when Melanie painted a sunrise.

**Judge Reasoning:** The reference answer provides a specific year (2022). The model's answer states it does not have enough information to determine the date, which is a direct contradiction of the factual information in the reference. Therefore, the model's answer is incorrect.

**Exact Match:** No

#### Example 3 (ID: 6)

**Reference:** The sunday before 25 May 2023

**Model Answer:** I don't have enough information to determine when Melanie ran a charity race.

**Judge Reasoning:** The reference answer provides a specific temporal point ('The sunday before 25 May 2023'), while the model answer states it lacks sufficient information. These are fundamentally incompatible; the model fails to provide the required temporal understanding.

**Exact Match:** No

#### Example 4 (ID: 7)

**Reference:** June 2023

**Model Answer:** I don't have enough information to answer when Melanie is planning on going camping.

**Judge Reasoning:** The reference answer provides a specific time ('June 2023'), while the model answer states it lacks the information to answer. These are directly contradictory; the model's answer is incorrect.

**Exact Match:** No

#### Example 5 (ID: 9)

**Reference:** The week before 9 June 2023

**Model Answer:** Based on the provided information, there is no specific mention of Caroline giving a speech at a school. Therefore, I don't have enough information to answer when this occurred.

**Judge Reasoning:** The model claims there is no information to answer, but the reference answer provides a specific temporal answer ('The week before 9 June 2023'). Therefore, the model's response is incorrect as it fails to provide the temporal information that exists in the reference.

**Exact Match:** No

*... and 314 more failures in this category*

### Reasoning & Inference (Category 3)

**Failures:** 94

#### Example 1 (ID: 3)

**Reference:** Psychology, counseling certification

**Model Answer:** Based on the provided context, Caroline would be likely to pursue fields in mathematics and computer science in her education.

**Judge Reasoning:** The model's answer (mathematics and computer science) is completely different from the reference answer (psychology, counseling certification). There is no overlap in meaning or inference, and the model's conclusion does not align with the provided reference.

**Exact Match:** No

#### Example 2 (ID: 15)

**Reference:** Likely no

**Model Answer:** I don't have enough information to determine if Caroline would still want to pursue counseling as a career without the support she received growing up.

**Judge Reasoning:** The reference answer provides a definitive inference ('Likely no'), while the model answer refuses to make an inference, stating it lacks information. For a Category 3 (Reasoning & Inference) question, the model's failure to draw the probable conclusion indicated in the reference means its answer is not correct, even if it is cautious. The task requires evaluating if the model's answer is correct compared to the reference, and here the conclusions do not match.

**Exact Match:** No

#### Example 3 (ID: 23)

**Reference:** Yes, since she collects classic children's books

**Model Answer:** Based on the provided information, there is no specific detail about Caroline having Dr. Seuss books on her bookshelf. Therefore, I don't have enough information to determine if Caroline would likely have Dr. Seuss books on her bookshelf.

**Judge Reasoning:** The model's answer is incorrect. The question is a reasoning and inference task. The reference answer provides the correct inference: if Caroline collects classic children's books, she would *likely* have Dr. Seuss books, as they are quintessential classics in that category. The model fails to make this logical connection and incorrectly states there is not enough information, demonstrating flawed reasoning.

**Exact Match:** No

#### Example 4 (ID: 28)

**Reference:** LIkely no; though she likes reading, she wants to be a counselor

**Model Answer:** I don't have enough information to determine if Caroline would pursue writing as a career option.

**Judge Reasoning:** The reference answer provides a clear inference based on stated preferences: Caroline likes reading but wants to be a counselor, leading to the conclusion 'likely no.' The model's answer ('I don't have enough information') is incorrect because the necessary information to make this inference is present in the reference context. The model failed to perform the required reasoning.

**Exact Match:** No

#### Example 5 (ID: 31)

**Reference:** Likely no, she does not refer to herself as part of it

**Model Answer:** Based on the provided information, there is no detail about Melanie's sexual orientation or gender identity, so I don't have enough information to determine if she would be considered a member of the LGBTQ community.

**Judge Reasoning:** The model's answer states there is not enough information to determine, which is a neutral, non-committal response. The reference answer, however, makes a specific inference ('Likely no') based on the character's own self-identification. Since the question type is Reasoning & Inference, the model's failure to draw the same conclusion from the implied context (that she does not refer to herself as part of it) means its reasoning does not match the reference. The model's answer is therefore incorrect.

**Exact Match:** No

*... and 89 more failures in this category*

### Detailed Understanding (Category 4)

**Failures:** 834

#### Example 1 (ID: 84)

**Reference:** self-care is important

**Model Answer:** Based on the provided information, there is no detail about what Melanie realized after the charity race.

**Judge Reasoning:** The model's answer states there is no detail about the realization, while the reference answer provides a specific realization ('self-care is important'). The model's claim of missing information is incorrect, as the reference directly answers the question. Therefore, the answers do not match in content.

**Exact Match:** No

#### Example 2 (ID: 85)

**Reference:** by carving out some me-time each day for activities like running, reading, or playing the violin

**Model Answer:** Based on the provided information, there are no specific details about how Melanie prioritizes self-care. Therefore, I don't have enough information to answer your question.

**Judge Reasoning:** The model claims there is no information, but the reference answer provides a specific method: carving out daily 'me-time' for activities like running, reading, or playing the violin. The model's answer is factually incorrect as it fails to capture these essential details from the source.

**Exact Match:** No

#### Example 3 (ID: 86)

**Reference:** researching adoption agencies

**Model Answer:** I don't have enough information about Caroline's plans for the summer.

**Judge Reasoning:** The model claims insufficient information, but the reference answer provides a specific and definitive plan ('researching adoption agencies'). This is a direct mismatch; the model failed to recall or provide the detailed information present in the reference.

**Exact Match:** No

#### Example 4 (ID: 87)

**Reference:** LGBTQ+ individuals

**Model Answer:** The provided context does not specify the type of individuals the adoption agency Caroline is considering supports.

**Judge Reasoning:** The model's answer claims the context does not specify the type of individuals, but the reference answer explicitly states 'LGBTQ+ individuals'. Therefore, the model's answer is incorrect as it fails to provide the specific detail present in the reference.

**Exact Match:** No

#### Example 5 (ID: 88)

**Reference:** because of their inclusivity and support for LGBTQ+ individuals

**Model Answer:** Based on the information provided, there are no details about why Caroline chose a specific adoption agency. Therefore, I don't have enough information to answer this question.

**Judge Reasoning:** The model claims there is no information to answer, but the reference answer provides a specific, detailed reason ('inclusivity and support for LGBTQ+ individuals'). Therefore, the model's answer is incorrect as it fails to provide the required detailed understanding from the source material.

**Exact Match:** No

*... and 829 more failures in this category*

### Unknown (Category 5)

**Failures:** 294

#### Example 1 (ID: 160)

**Reference:** 

**Model Answer:** Based on the information provided, I don't have enough details to specify what grandma's gift to Melanie was.

**Judge Reasoning:** The model's answer states it does not have enough information to specify the gift. The reference answer, however, provides a specific gift ('a necklace'). Since the model fails to provide this factual detail, the answer is incorrect. This appears to be a Category 1 (Factual Recall) question.

**Exact Match:** No

#### Example 2 (ID: 161)

**Reference:** 

**Model Answer:** Based on the information provided, I don't have enough details to specify what grandpa's gift to Caroline was.

**Judge Reasoning:** The model explicitly states it does not have the information to answer the question, while the reference answer provides a specific response. This is a direct mismatch; the model's answer is non-committal and incorrect when compared to the factual recall expected in the reference.

**Exact Match:** No

#### Example 3 (ID: 162)

**Reference:** 

**Model Answer:** Based on the information provided, I don't have enough details to answer what Caroline's hand-painted bowl is a reminder of.

**Judge Reasoning:** The model's answer states it lacks information to answer the question. The reference answer, however, provides a specific piece of information. Since the model fails to provide the factual content present in the reference, it is incorrect. The question type is unknown, but the model's non-answer cannot match a substantive reference.

**Exact Match:** No

#### Example 4 (ID: 165)

**Reference:** 

**Model Answer:** I don't have enough information to answer that question.

**Judge Reasoning:** The model's answer ('I don't have enough information') is a refusal to answer, while the reference answer provides a specific piece of information. For the model's answer to be correct, it would need to state the type of workshop (e.g., 'career counseling' or a similar specific detail) as indicated in the reference. Since it does not, it is incorrect.

**Exact Match:** No

#### Example 5 (ID: 167)

**Reference:** 

**Model Answer:** Based on the provided context, there is no information about the kind of place Melanie wants to create for people.

**Judge Reasoning:** The model's answer claims there is no information in the provided context, but the reference answer contains a specific claim. Since the model explicitly states it cannot answer due to lack of information, while the reference provides an answer, the model's response is incorrect by default. The question type is unknown, but the core failure is the model's inability to provide the information that the reference asserts exists.

**Exact Match:** No

*... and 289 more failures in this category*

## Insights & Recommendations

❌ **Needs Improvement:** The system struggles with long-term memory tasks.

📊 **LLM Judge Benefit:** LLM scoring found 8.3% more correct answers than exact match, 
indicating the system produces semantically correct answers that differ in phrasing.

🎯 **Strongest Area:** Unknown (34.1% accuracy)
🔧 **Needs Work:** Temporal Understanding (0.6% accuracy)

### Recommendations

- **Factual Recall:** Improve entity extraction and graph storage reliability
- **Temporal Understanding:** Enhance temporal entity recognition and date normalization
- **Reasoning:** Strengthen multi-hop retrieval and inference capabilities
- **Detailed Understanding:** Improve context preservation and detail retention

---

*This report was generated automatically by the LoCoMo evaluation pipeline.*