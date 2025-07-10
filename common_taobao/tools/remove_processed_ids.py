# remove_processed_ids.py
def main():
    processed_file = r'C:\Users\martin\Desktop\keyword\exist.txt'
    to_process_file = r'C:\Users\martin\Desktop\keyword\process.txt'
    output_file = r'C:\Users\martin\Desktop\keyword\filtered_ids.txt'

    # 读取已处理的商品ID
    with open(processed_file, 'r', encoding='utf-8') as f:
        processed_ids = set(line.strip() for line in f if line.strip())

    # 读取待处理的商品ID
    with open(to_process_file, 'r', encoding='utf-8') as f:
        to_process_ids = [line.strip() for line in f if line.strip()]

    # 去除已处理ID
    remaining_ids = [id_ for id_ in to_process_ids if id_ not in processed_ids]

    # 写入结果
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(remaining_ids))

    print(f'✅ 处理完成，共 {len(remaining_ids)} 个未处理ID，已写入 {output_file}')

if __name__ == '__main__':
    main()
