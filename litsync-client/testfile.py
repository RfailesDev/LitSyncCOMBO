print("123")
print("hello world")

all_max = 0

def count(a, all_max=None):
    all_max + a
    return all_max

for i in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
    print(i)
    all_max = count(i, all_max=all_max)

print(all_max)
print("DONE")