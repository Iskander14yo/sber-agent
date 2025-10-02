from pathlib import Path


RSS_LINKS = {
    "AI": "https://www.google.com/alerts/feeds/02312135717193987710/2532276790151932469",
}

API_KEY = ""

ALERTS_FOLDER = Path("alerts")
CONTENTS_FOLDER = Path("contents")
RESPONSES_1_FOLDER = Path("responses_1")
RESPONSES_2_FOLDER = Path("responses_2")
FINAL_FOLDER = Path("final")

# Можно будет потом поменять на thresholds
FEEDS_COUNT_AFTER_TITLE_AND_CONTENT_FILTER = 50  # алерты, в которых модель уверена, что они релевантны
FEEDS_COUNT_CONFUSED = 10  # алерты, в которых модель не уверена

WHAT_IS_IMPORTANT = """
Below I will give you a description of what I'm interested in.

The collections usually consist of news on:
1. New draft laws and regulatory initiatives in other countries 
2. Court cases (usually copyright)
3. Some initiatives in the UN, OECD, etc. to coordinate international activities in the field of AI regulation
4. Investigation by state authorities of the activities of AI chatbots
5. Any reports from cool international organizations on the topic of AI regulation 
6. Proposals of AI companies in the field of regulation 

Accordingly, the text of the news may contain the following keywords: 

1. New draft laws and regulatory initiatives
 • Legislation: AI Act, AI Bill, Artificial Intelligence Regulation, draft law, legislative proposal, bill, regulatory framework, directive, ordinance, policy, guidelines, published bill, draft law, regulations, initiative.
 • Clarifying words: AI Act, Europe, USA, California, Congress, Parliament, Senate, Duma, Government 

2. Court cases 
 • Litigation: lawsuit, case, litigation, court ruling, class action, complaint, plaintiffs, statement of claim, court, court decision.
 • Intellectual property: copyright, patent, trademark, infringement, plagiarism, intellectual property.
 • Data precedents: data scraping, privacy lawsuit, antitrust, monopolistic practices.

3. Initiatives of the United Nations, the OECD and other international organizations
 • Organizations: UN, United Nations, UNESCO, OECD, OECD AI Principles, ITU, UN General Assembly, G20, G7, Council of Europe.
 • Keywords: global governance, international agreement, global principles, convention, moratorium, treaty, charter, international initiative, joint statement.

4. Government investigations into AI chatbots and services
 • Regulators: investigation, inquiry, probe, investigates, regulator, watchdog, FTC, DOJ, CMA, European Commission, FAS, Roskomnadzor, data protection authority, privacy regulator.
 • Reasons for investigation: privacy breach, data leak, bias, misuse, consumer protection, antitrust, safety, compliance, responsible AI, violation, complaint.

5. Reports and analysis of international organizations
 • Formats: report, white paper, study, analysis, survey, index, framework, recommendations, policy paper, research, report, report, article, study.
 • Reputable sources: OECD, World Economic Forum, OpenAI, Chatham House, Turing Institute, Stanford HAI, NIST, ISO, review, index.

6. Proposals and initiatives of companies
 • Commercial proposals: policy proposal, voluntary commitments, AI governance framework, responsible AI pledge, model card, safety charter, AI governance plan, proposal, commitment, initiative.
 • Companies: OpenAI, Anthropic, Google, Meta, Microsoft, Apple, xAI, NVIDIA, Alibaba, Baidu, Yandex, Sberbank, VK.
"""

FILTER_BY_TITLE_AND_CONTENT_PROMPT = """
You are a helpful assistant and your goal is to filter alerts that are relevant to the user's interests.
Here you are given a json with links like {{id, title, content}}. You need to return two lists (valid JSON format):
1) "relevant_ids":List of ids that you are 100% sure are relevant to the user's interests
Max length of the list is {FEEDS_COUNT_AFTER_TITLE_AND_CONTENT_FILTER}
2) "unsure_ids": List of ids that you are not sure are relevant to the user's interests
Max length of the list is {FEEDS_COUNT_CONFUSED}

{WHAT_IS_IMPORTANT}
""".format(
    WHAT_IS_IMPORTANT=WHAT_IS_IMPORTANT,
    FEEDS_COUNT_AFTER_TITLE_AND_CONTENT_FILTER=FEEDS_COUNT_AFTER_TITLE_AND_CONTENT_FILTER,
    FEEDS_COUNT_CONFUSED=FEEDS_COUNT_CONFUSED,
)


FILTER_BY_TEXT_PROMPT = """
You are a helpful assistant and your goal is to filter alerts that are relevant to the user's interests.
Here you are given a text. If you think it is relevant to the user's interests, return a list (valid JSON format) with rewritten title and a short summary of the news. Otherwise, return an empty list.
Title and summary needs to be in Russian language. Factually correct, grammatically correct, without any additional information. Just summarization. Title needs to be a full rich sentence. Summary needs to be 2-3 sentences.

Example is following:
{{
    "title": "Вышел новый отчет о влиянии генеративного ИИ на рынок труда.",
    "summary": "Новый отчет Budget Lab при Йельском университете и Института Брукингса анализирует влияние генеративного ИИ на рынок труда с момента запуска ChatGPT в ноябре 2022 года. Отчет показывает стабильность, а не масштабные сокращения, вопреки распространенным опасениям. Авторы подчеркивают важность постоянного мониторинга и призывают ведущие ИИ-компании (такие как Google, Microsoft, OpenAI и Anthropic) прозрачно и ответственно делиться данными об использовании ИИ, чтобы политики могли принимать обоснованные решения относительно будущего труда."
}}

{WHAT_IS_IMPORTANT}
""".format(
    WHAT_IS_IMPORTANT=WHAT_IS_IMPORTANT,
)

