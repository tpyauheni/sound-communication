import os.path as p
import pyggwave
import ast

import xlwt
from xlwt import Workbook

data_dict = {}
data_dict2 = {}


def read_to_dict(file_name, dict):
    with open(p.join(p.dirname(p.abspath(__file__)), file_name)) as file:
        for line in file.readlines():
            skip = True

            if 'Writing data' in line and 'Verbose (frame)' in line:
                skip = False

            if 'Received data' in line and 'Verbose (frame)' in line:
                skip = False

            if skip:
                continue

            ls = line.split()

            if len(ls) < 2:
                continue

            dtime = ls[1].split(':')

            if len(dtime) != 3:
                continue

            dtime = [float(x) for x in dtime]
            secs_time = dtime[2]
            data_index = line.index(' data: ')
            data_str = line[data_index + 7:]
            data = ast.literal_eval(data_str)
            dict[data.hex()] = (dtime, 'Writing data' in line, len(data), pyggwave.raw__get_ecc_bytes_for_length(len(data)))


def merge_dicts(dict1, dict2, callback, input_changer):
    data = []

    for k, v1 in dict1.items():
        if k in dict2:
            v2 = dict2[k]

            if v1[1] == v2[1]:
                continue

            sender = v1 if v1[1] else v2
            receiver = v2 if v1[1] else v1
            sender_secs = sender[0][0] * 3600 + sender[0][1] * 60 + sender[0][2]
            receiver_secs = receiver[0][0] * 3600 + receiver[0][1] * 60 + receiver[0][2]

            if sender_secs > receiver_secs:
                continue

            if receiver_secs - sender_secs > 3.0:
                continue

            data.append((sender, receiver))

    input_changer(data)

    for element in data:
        callback(*element)


wb = Workbook()
sheet1 = wb.add_sheet('Auto-generated data')
sheet1.write(0, 0, 'Sender time')
sheet1.write(0, 1, 'Receiver time')
sheet1.write(0, 2, 'Time delta')
sheet1.write(0, 3, 'Packet size')
sheet1.write(0, 4, 'Error correction size')
sheet1.write(0, 5, 'Total size')
sheet1.write(0, 6, 'Average speed')
y = 1


def write_to_excel(sender, receiver):
    global y
    sender_time = sender[0][2]
    receiver_time = receiver[0][2] + (60 if sender[0][1] < receiver[0][1] else 0)
    sheet1.write(y, 0, sender_time)
    sheet1.write(y, 1, receiver_time)
    delta_time = receiver_time - sender_time
    sheet1.write(y, 2, delta_time)
    sheet1.write(y, 3, sender[2])
    sheet1.write(y, 4, sender[3])
    total_size = sender[2] + sender[3] + 6
    sheet1.write(y, 5, total_size)
    sheet1.write(y, 6, total_size / delta_time * 8)
    print(f'Row {y}:', sender, receiver)
    y += 1
    return


read_to_dict('log.txt', data_dict)
read_to_dict('log2.txt', data_dict2)
merge_dicts(
    data_dict,
    data_dict2,
    write_to_excel,
    lambda x: x.sort(
        key=lambda y: y[0][2]
    ),
)
wb.save('generated.xlsx')

# print(data_dict)
