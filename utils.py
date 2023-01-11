def dict_factory(crsr, row):
    fields = [column[0] for column in crsr.description]
    return {key: value for key, value in zip(fields, row)}