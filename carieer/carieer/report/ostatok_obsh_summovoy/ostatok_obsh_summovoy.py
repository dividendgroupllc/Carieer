# Ostatok Obsh Summovoy ("ОСТАТОК ОБЩ суммовой"): har bir tovarning har oy oxiridagi qoldig'i SUMMADA (tan narxda, so'm)
# - oyma-oy ustunlar. Tepada jadvaldagi kabi: «Итого» (barcha tovarlar), «Баланс» (ombor hisoblari - Stock - qoldig'i)
# va «Разница» (Итого - Баланс; to'g'ri yuritilganda 0). Miqdordagi ko'rinishi - «ОСТАТОК ОБЩ» (Ostatok Obsh).

from carieer.carieer.report.ostatok_obsh.ostatok_obsh import build


def execute(filters=None):
	return build(filters, summa=True)
