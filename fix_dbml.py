import subprocess
import re

result = subprocess.run(['git', 'show', 'HEAD:crescendo_schema.dbml'], capture_output=True, text=True)
original_dbml = result.stdout

refs = re.findall(r'^Ref:\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*([<>\-])\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*\[(.*?)\]', original_dbml, re.MULTILINE)

ref_dict = {}
for src_table, src_col, op, tgt_table, tgt_col, options in refs:
    if src_table not in ref_dict:
        ref_dict[src_table] = {}
    rule = options.replace('delete: ', 'ON DELETE ').upper()
    ref_dict[src_table][src_col] = f'ref: {op} {tgt_table}.{tgt_col}, note: \'{rule}\''

with open('crescendo_schema.dbml', 'r') as f:
    current_lines = f.readlines()

output_lines = []
current_table = None

for line in current_lines:
    table_match = re.match(r'^Table\s+([a-zA-Z0-9_]+)', line)
    if table_match:
        current_table = table_match.group(1)
        output_lines.append(line)
        continue
        
    if current_table and current_table in ref_dict:
        for col_name, ref_str in ref_dict[current_table].items():
            if re.match(r'^\s*' + col_name + r'\s+[a-zA-Z0-9_]+', line):
                line = re.sub(r',\s*note:\s*\'DELETE:\s*[^>]+\'', '', line)
                if '[' in line:
                    line = line.replace(']', f', {ref_str}]')
                else:
                    line = line.replace('\n', f' [{ref_str}]\n')
                break
                
    output_lines.append(line)

final_lines = []
for line in output_lines:
    if 'O2O link to users for claimed profiles' in line:
        final_lines.append("  user_id integer [null, unique, ref: - users.id, note: 'O2O link to users for claimed profiles, ON DELETE SET NULL']\n")
    else:
        final_lines.append(line)

with open('crescendo_schema.dbml', 'w') as f:
    f.writelines(final_lines)
