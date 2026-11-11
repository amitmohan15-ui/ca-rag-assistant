import csv

# 35 Benchmark questions for Chartered Accountant domain / Companies Act 2013
# 30 grounded questions across direct lookup, comparison, and explanation
# 5 unanswerable out-of-scope questions (GST, Stamp duty, Income Tax, etc.)
rows = [
    {
        "id": 1,
        "question": "What is the threshold for a company to constitute an audit committee?",
        "expected_answer": "The Board of Directors of every listed company and such other class or classes of companies as may be prescribed shall constitute an Audit Committee.",
        "expected_source": "Companies Act 2013, Sec 177, p. 108",
        "answerable": "yes"
    },
    {
        "id": 2,
        "question": "What is the composition requirement for an Audit Committee under Section 177?",
        "expected_answer": "The Audit Committee shall consist of a minimum of three directors with independent directors forming a majority, and majority of members including Chairperson must have ability to read and understand financial statements.",
        "expected_source": "Companies Act 2013, Sec 177, p. 109",
        "answerable": "yes"
    },
    {
        "id": 3,
        "question": "What are the restrictions on advancing loans to directors under Section 185?",
        "expected_answer": "No company shall, directly or indirectly, advance any loan, including any loan represented by a book debt, to any of its directors or to any other person in whom the director is interested, or give any guarantee or provide any security in connection with any loan taken by him or such other person, except as specifically permitted.",
        "expected_source": "Companies Act 2013, Sec 185, p. 114",
        "answerable": "yes"
    },
    {
        "id": 4,
        "question": "What is the net profit threshold that triggers Corporate Social Responsibility (CSR) obligations under Section 135?",
        "expected_answer": "Every company having net worth of rupees 500 crore or more, or turnover of rupees 1000 crore or more, or a net profit of rupees 5 crore or more during immediately preceding financial year shall constitute a CSR Committee.",
        "expected_source": "Companies Act 2013, Sec 135, p. 87",
        "answerable": "yes"
    },
    {
        "id": 5,
        "question": "How much amount must a company spend on CSR activities under Section 135?",
        "expected_answer": "At least two per cent of the average net profits of the company made during the three immediately preceding financial years.",
        "expected_source": "Companies Act 2013, Sec 135, p. 87",
        "answerable": "yes"
    },
    {
        "id": 6,
        "question": "Who is eligible to be appointed as an auditor of a company under Section 141?",
        "expected_answer": "A person shall be eligible for appointment as an auditor of a company only if he is a chartered accountant in practice. A firm whereof majority of partners practicing in India are qualified for appointment may be appointed.",
        "expected_source": "Companies Act 2013, Sec 141, p. 89",
        "answerable": "yes"
    },
    {
        "id": 7,
        "question": "What are the disqualifications for an auditor under Section 141(3)?",
        "expected_answer": "Disqualifications include a body corporate (other than LLP), officer/employee of the company, partner/employee of an officer, person or partner holding security or indebted beyond prescribed limit, or convicted of offence involving fraud.",
        "expected_source": "Companies Act 2013, Sec 141, p. 89",
        "answerable": "yes"
    },
    {
        "id": 8,
        "question": "What is the tenure of appointment of an individual auditor and an audit firm under Section 139?",
        "expected_answer": "An individual auditor can be appointed for not more than one term of five consecutive years, and an audit firm for not more than two terms of five consecutive years.",
        "expected_source": "Companies Act 2013, Sec 139, p. 86",
        "answerable": "yes"
    },
    {
        "id": 9,
        "question": "What is the procedure for resignation of an auditor under Section 140?",
        "expected_answer": "The auditor who has resigned shall file within thirty days from the date of resignation a statement in prescribed form with the company and the Registrar indicating reasons and other facts.",
        "expected_source": "Companies Act 2013, Sec 140, p. 88",
        "answerable": "yes"
    },
    {
        "id": 10,
        "question": "What are the auditor's duties regarding reporting on fraud under Section 143(12)?",
        "expected_answer": "If an auditor has reason to believe that an offence of fraud involving such amount as may be prescribed is being or has been committed against the company by officers or employees, the auditor shall report the matter to the Central Government.",
        "expected_source": "Companies Act 2013, Sec 143, p. 93",
        "answerable": "yes"
    },
    {
        "id": 11,
        "question": "What is the minimum number of board meetings a company must hold each year under Section 173?",
        "expected_answer": "Every company shall hold a minimum number of four meetings of its Board of Directors every year in such a manner that not more than one hundred and twenty days shall intervene between two consecutive meetings.",
        "expected_source": "Companies Act 2013, Sec 173, p. 107",
        "answerable": "yes"
    },
    {
        "id": 12,
        "question": "What is the quorum for a Board of Directors meeting under Section 174?",
        "expected_answer": "The quorum for a meeting of the Board of Directors shall be one-third of its total strength or two directors, whichever is higher.",
        "expected_source": "Companies Act 2013, Sec 174, p. 108",
        "answerable": "yes"
    },
    {
        "id": 13,
        "question": "What is the maximum number of directorships an individual can hold under Section 165?",
        "expected_answer": "No person shall hold office as a director, including any alternate directorship, in more than twenty companies at the same time, of which maximum directorships in public companies shall not exceed ten.",
        "expected_source": "Companies Act 2013, Sec 165, p. 105",
        "answerable": "yes"
    },
    {
        "id": 14,
        "question": "What are the grounds for disqualification of a director under Section 164?",
        "expected_answer": "Disqualifications include being of unsound mind, undischarged insolvent, convicted of an offence involving moral turpitude with imprisonment not less than six months, failure to pay calls on shares, or failure to file financial statements for three consecutive financial years.",
        "expected_source": "Companies Act 2013, Sec 164, p. 104",
        "answerable": "yes"
    },
    {
        "id": 15,
        "question": "What duties of directors are codified under Section 166?",
        "expected_answer": "A director shall act in good faith to promote objects of company for benefit of members as a whole, exercise reasonable care and skill, avoid direct or indirect conflicts of interest, and not achieve undue gain.",
        "expected_source": "Companies Act 2013, Sec 166, p. 105",
        "answerable": "yes"
    },
    {
        "id": 16,
        "question": "When does the office of a director become vacant under Section 167?",
        "expected_answer": "Office becomes vacant if he incurs any disqualification under section 164, absents himself from all Board meetings held during twelve months with or without leave, acts in contravention of section 184, or is convicted by court.",
        "expected_source": "Companies Act 2013, Sec 167, p. 106",
        "answerable": "yes"
    },
    {
        "id": 17,
        "question": "What are the statutory requirements for disclosure of interest by a director under Section 184?",
        "expected_answer": "Every director shall disclose his concern or interest in any company, body corporate, firm or association at the first meeting of the Board in which he participates as director and at the first Board meeting of every financial year.",
        "expected_source": "Companies Act 2013, Sec 184, p. 113",
        "answerable": "yes"
    },
    {
        "id": 18,
        "question": "What is the limit for inter-corporate loans and investments under Section 186 without special resolution?",
        "expected_answer": "A company cannot give loan, guarantee, security, or acquire securities exceeding 60% of its paid-up share capital, free reserves and securities premium account or 100% of its free reserves and securities premium account, whichever is more, without prior approval by special resolution.",
        "expected_source": "Companies Act 2013, Sec 186, p. 115",
        "answerable": "yes"
    },
    {
        "id": 19,
        "question": "What approvals are required for Related Party Transactions under Section 188?",
        "expected_answer": "Consent of Board of Directors is required at a meeting of Board, and prior approval of company by resolution is required for transactions exceeding prescribed limits.",
        "expected_source": "Companies Act 2013, Sec 188, p. 117",
        "answerable": "yes"
    },
    {
        "id": 20,
        "question": "What is the overall maximum limit on managerial remuneration payable by a public company under Section 197?",
        "expected_answer": "The total managerial remuneration payable by a public company to its directors, including managing director and whole-time director, in respect of any financial year shall not exceed eleven per cent of the net profits.",
        "expected_source": "Companies Act 2013, Sec 197, p. 123",
        "answerable": "yes"
    },
    {
        "id": 21,
        "question": "Which companies are required to appoint Key Managerial Personnel (KMP) under Section 203?",
        "expected_answer": "Every listed company and every other public company having a paid-up share capital of ten crore rupees or more shall have whole-time key managerial personnel: MD/CEO/manager, company secretary, and CFO.",
        "expected_source": "Companies Act 2013, Sec 203, p. 128",
        "answerable": "yes"
    },
    {
        "id": 22,
        "question": "What is the provision for Secretarial Audit for bigger companies under Section 204?",
        "expected_answer": "Every listed company and other prescribed classes of companies shall annex with its Board's report a secretarial audit report given by a company secretary in practice.",
        "expected_source": "Companies Act 2013, Sec 204, p. 129",
        "answerable": "yes"
    },
    {
        "id": 23,
        "question": "What is the timeframe for holding an Annual General Meeting (AGM) under Section 96?",
        "expected_answer": "Every company shall hold an AGM within six months from the date of closing of the financial year, and not more than fifteen months shall elapse between the date of one AGM and that of the next.",
        "expected_source": "Companies Act 2013, Sec 96, p. 66",
        "answerable": "yes"
    },
    {
        "id": 24,
        "question": "What are the rules regarding declaration and payment of dividend under Section 123?",
        "expected_answer": "Dividend shall be declared or paid by a company only out of profits of the company for that year arrived at after providing for depreciation, or out of profits for previous financial years after depreciation, or money provided by Government.",
        "expected_source": "Companies Act 2013, Sec 123, p. 77",
        "answerable": "yes"
    },
    {
        "id": 25,
        "question": "What are the requirements for financial statements under Section 129?",
        "expected_answer": "The financial statements shall give a true and fair view of the state of affairs of the company, comply with accounting standards notified under section 133, and be in the form provided in Schedule III.",
        "expected_source": "Companies Act 2013, Sec 129, p. 81",
        "answerable": "yes"
    },
    {
        "id": 26,
        "question": "Who is required to sign the financial statements of a company under Section 134?",
        "expected_answer": "Financial statements shall be signed on behalf of Board by chairperson authorized by Board or two directors (one managing director), and CEO, CFO and company secretary if appointed.",
        "expected_source": "Companies Act 2013, Sec 134, p. 82",
        "answerable": "yes"
    },
    {
        "id": 27,
        "question": "What is the prohibition on acceptance of deposits from public under Section 73?",
        "expected_answer": "No company shall invite, accept or renew deposits under this Act from the public except in a manner provided under Chapter V, though a company may accept deposits from its members subject to passing a resolution and fulfilling conditions.",
        "expected_source": "Companies Act 2013, Sec 73, p. 57",
        "answerable": "yes"
    },
    {
        "id": 28,
        "question": "What are the contents and filing deadline of the Annual Return under Section 92?",
        "expected_answer": "Every company shall prepare an annual return in prescribed form and file it with Registrar within sixty days from the date on which AGM is held.",
        "expected_source": "Companies Act 2013, Sec 92, p. 64",
        "answerable": "yes"
    },
    {
        "id": 29,
        "question": "What is the maximum term and tenure for an Independent Director under Section 149?",
        "expected_answer": "An independent director shall hold office for a term up to five consecutive years, and shall be eligible for re-appointment on passing special resolution, but cannot hold office for more than two consecutive terms.",
        "expected_source": "Companies Act 2013, Sec 149, p. 98",
        "answerable": "yes"
    },
    {
        "id": 30,
        "question": "What is the short title, extent and commencement of the Companies Act 2013 under Section 1?",
        "expected_answer": "This Act may be called the Companies Act, 2013. It extends to the whole of India. Section 1 came into force at once and remaining provisions on notification.",
        "expected_source": "Companies Act 2013, Sec 1, p. 14",
        "answerable": "yes"
    },
    {
        "id": 31,
        "question": "What is the GST rate on legal services?",
        "expected_answer": "not found",
        "expected_source": "not found",
        "answerable": "no"
    },
    {
        "id": 32,
        "question": "What is the stamp duty payable on conveyance deed in Maharashtra under Bombay Stamp Act?",
        "expected_answer": "not found",
        "expected_source": "not found",
        "answerable": "no"
    },
    {
        "id": 33,
        "question": "What is the tax rate applicable on long term capital gains under Section 112A of Income Tax Act 1961?",
        "expected_answer": "not found",
        "expected_source": "not found",
        "answerable": "no"
    },
    {
        "id": 34,
        "question": "What is the TDS rate under Section 194J for technical services?",
        "expected_answer": "not found",
        "expected_source": "not found",
        "answerable": "no"
    },
    {
        "id": 35,
        "question": "What is the minimum wages rate for semi-skilled labour under the Code on Wages 2019?",
        "expected_answer": "not found",
        "expected_source": "not found",
        "answerable": "no"
    }
]

with open("golden_set.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)

print(f"Successfully generated golden_set.csv with {len(rows)} benchmark rows.")

