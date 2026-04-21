import openpyxl,sys
f=r"c:\Users\Miguel Martinez SSD\OneDrive - BROWSER TRAVEL SOLUTIONS S.A.S VIAJEMOS\Documentos\PROYECTOS\CARGUE MASIVO VJM Y MCR\LANDINGS EJEMPLO MCR\CIUDADES\09-01-2025 Cargue de Contenido Memphis.xlsx"
wb=openpyxl.load_workbook(f,data_only=True,read_only=True)
ws=wb["Secciones"]
g=lambda v:"" if v is None else str(v).strip()
w=lambda t:len(t.split()) if t else 0
for r in ws.iter_rows(min_row=28,max_row=39,min_col=1,max_col=8,values_only=False):
    n=r[0].row;a=g(r[0].value);b=g(r[1].value);c=g(r[2].value);d=g(r[3].value);e=g(r[4].value);ff=g(r[5].value)
    print(f"R{n}|A:{a}|B:{b}|F:{ff}|WC:{w(c)}/{w(d)}/{w(e)}")
    print(f"ES:{c}")
    print(f"EN:{d}")
    print(f"PT:{e}")
    print("---")
wb.close()
print("DONE1")
