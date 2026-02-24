import pandas as pd
from pathlib import Path
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

client = OpenAI(
    api_key="sk-vAVMNfz8aOIP9s1o2dFc4f009d5d4e8cBe4b56E52861C02b",
    base_url="https://api.gpt.ge/v1/",
    default_headers={"x-foo": "true"}
)


def search_fn(query):
    try:
        completion = client.chat.completions.create(
            model="gemini-3-flash-preview-search",
            messages=[{"role": "user", "content": query}],
        )
        return completion.choices[0].message.content
    except Exception as e:
        return 'NONE'


def find_citation_description(paper_a_title: str, paper_b_title: str, paper_b_url: str):
    authors_query = (
        f"请搜索论文《{paper_a_title}》的所有作者，"
        f"只需按顺序列出作者姓名，不需要任何介绍或其他信息。"
        f"格式如：作者1, 作者2, 作者3, ..."
    )
    authors_result = search_fn(authors_query)

    citation_query = (
        f"请访问以下链接，阅读论文《{paper_b_title}》的全文：{paper_b_url}\n\n"
        f"阅读全文后，找出该论文在正文中引用《{paper_a_title}》({authors_result})时的具体描述或表述。"
        f"要求：\n"
        f"1. 只摘录论文B原文中真实存在的对《{paper_a_title}》的引用描述，不能编造。\n"
        f"2. 请直接引用原文中的相关句子或段落，并注明出现在论文的哪个部分（如Introduction、Related Work等）。\n"
        f"3. 只需表述原文在哪个部分对《{paper_a_title}》进行了怎样的引用描述即可。如是正面描述，则需强调。\n"
        f"4. 如果找不到引用，只需输出'无法找到相关引用描述'。"
    )
    citation_result = search_fn(citation_query)

    return {
        "paper_a_authors": authors_result,
        "citation_description": citation_result,
    }


def process_row(args):
    i, paper_a_title, paper_b_title, paper_b_url = args
    result = find_citation_description(paper_a_title, paper_b_title, paper_b_url)
    return i, result


if __name__ == "__main__":
    PAPER_A_TITLE = "Detecting rotated objects as gaussian distributions and its 3-d generalization"

    file = '/Users/charlesyang/Desktop/files/google-scholar-scraper-master/data/excel/paper-20260224_031130_author_information.xlsx'
    df = pd.read_excel(file)
    df['Citing_Paper'] = PAPER_A_TITLE
    df['Citing_Description'] = ''

    tasks = [
        (i, PAPER_A_TITLE, df.loc[i, 'Paper_Title'], df.loc[i, 'Paper_Link'])
        for i in range(len(df))
    ]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_row, task): task[0] for task in tasks}

        with tqdm(total=len(tasks), desc="处理进度", unit="篇",colour='green') as pbar:
            for future in as_completed(futures):
                try:
                    i, result = future.result()
                    df.at[i, 'Citing_Description'] = result['citation_description']
                except Exception as e:
                    i = futures[future]
                    df.at[i, 'Citing_Description'] = f'处理异常: {e}'
                finally:
                    pbar.update(1)

    input_file = Path(file)
    outpath = input_file.with_stem(input_file.stem + "_with_citing_description")
    df.to_excel(outpath, index=False)
    print("全部完成，已保存至 citing_description.xlsx")