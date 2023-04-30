import sqlparse
from collections import OrderedDict


def sql_pred_parse(pred):
    # parse sql results and fix general errors

    # fix for no states
    no_state_sql = [' WHERE ;', 'WHERE ;', ' WHERE ', 'WHERE ', ' WHERE', 'WHERE']
    if pred in no_state_sql:
        return {}

    # 다중 도메인에 대한 JOIN 연산 completion은 공백으로 처리
    if 'JOIN' in pred:
        return {}

    pred = " * FROM " + pred
    
    # 세미콜론(;) 이후의 문자열 제거
    pred = pred.split(";")[0]
    
    # LIMIT이 이후의 문자열 제거
    if 'LIMIT' in pred:
        pred = pred.split('LIMIT')[0]

    # ORDER BY 이후의 문자열 제거
    if 'ORDER BY' in pred:
        pred = pred.split('ORDER BY')[0]

    # 쌍따옴표를 따옴표로
    if '\"' in pred:
        pred = pred.replace('\"', '\'')

    # completion 뒤에 가끔씩 공백 붙는 경우 존재
    pred = pred.strip()

    # Here we need to write a parser to convert back to dialogue state
    pred_slot_values = []
    # pred = pred.lower()
    parsed = sqlparse.parse(pred)
    if not parsed:
        return {}
    stmt = parsed[0]
    sql_toks = pred.split()
    operators = [" = ", " LIKE ", " < ", " > ", " >= ", " <= ", "="]

    if "AS" in pred:
        as_indices = [i for i, x in enumerate(sql_toks) if x == "AS"]

        table_name_map_dict = {}
        for indice in as_indices:
            table_name_map_dict[sql_toks[indice + 1].replace(",", "")] = sql_toks[indice - 1]

        slot_values_str = str(stmt.tokens[-1]).replace("_", " ").replace("""'""", "").replace("WHERE ", "")
        for operator in operators:
            slot_values_str = slot_values_str.replace(operator, "-")
        slot_values = slot_values_str.split(" AND ")

        for sv in slot_values:
            for t_ in table_name_map_dict.keys():
                sv = sv.replace(t_ + ".", table_name_map_dict[t_] + "-")
            pred_slot_values.append(sv)
    else:

        table_name = sql_toks[sql_toks.index("FROM") + 1]

        slot_values_str = str(stmt.tokens[-1]).replace("_", " ").replace("""'""", "").replace("WHERE ", "")
        for operator in operators:
            slot_values_str = slot_values_str.replace(operator, "-")
        slot_values = slot_values_str.split(" AND ")

        # IS NOT NULL이 붙는 경우 제거
        if 'NULL' in slot_values[-1]:
            del slot_values[-1]
        
        # [insert appropriate time]과 같은 경우 제거
        if '[' in slot_values[-1]:
            del slot_values[-1]

        pred_slot_values.extend([table_name + "-" + sv for sv in slot_values if slot_values != ['']])

    pred_slot_values = {'-'.join(sv_pair.split('-')[:-1]): sv_pair.split('-')[-1] for sv_pair in pred_slot_values}

    # value 소문자화
    for key in pred_slot_values:
        pred_slot_values[key] = pred_slot_values[key].lower()

    # remove _ in SQL columns
    pred_slot_values = {slot.replace('_', ' '): value for slot, value in pred_slot_values.items()}

    # fix typos
    # pred_slot_values, _ = typo_fix(pred_slot_values)

    return pred_slot_values


def sv_dict_to_string(svs, sep=' ', sort=True):
    result_list = [f"{s.replace('-', sep)}{sep}{v}" for s, v in svs.items()]
    if sort:
        result_list = sorted(result_list)
    return ', '.join(result_list)


def slot_values_to_seq_sql(original_slot_values, single_answer=False):
    sql_str = ""
    tables = OrderedDict()
    col_value = dict()

    # add '_' in SQL columns
    slot_values = {}
    for slot, value in original_slot_values.items():
        if ' ' in slot:
            slot = slot.replace(' ', '_')
        slot_values[slot] = value

    for slot, value in slot_values.items():
        assert len(slot.split("-")) == 2

        if '|' in value:
            value = value.split('|')[0]

        table, col = slot.split("-")  # slot -> table-col

        if table not in tables.keys():
            tables[table] = []
        tables[table].append(col)

        # sometimes the answer is ambiguous
        if single_answer:
            value = value.split('|')[0]
        col_value[slot] = value

    # When there is only one table
    if len(tables.keys()) == 1:
        where_clause = []
        table = list(tables.keys())[0]
        for col in tables[table]:
            where_clause.append("{} = {}".format(col, col_value["{}-{}".format(table, col)]))
        sql_str = "SELECT * FROM {} WHERE {}".format(table, " AND ".join(where_clause))
    # When there are more than one table
    else:
        # We observed that Codex has variety in the table short names, here we just use a simple version.
        from_clause = []
        where_clause = []
        for i, table in enumerate(tables.keys()):
            t_i = "t{}".format(i + 1)
            from_clause.append("{} AS {}".format(table, t_i))
            for col in tables[table]:
                where_clause.append("{}.{} = {}".format(t_i, col, col_value["{}-{}".format(table, col)]))
        sql_str = "SELECT * FROM {} WHERE {}".format(", ".join(from_clause), " AND ".join(where_clause))

    return sql_str
