import csv
import sys
from tkinter import *
from tkinter import ttk
from tkinter import font


root = Tk()
w, h = root.winfo_screenwidth(), root.winfo_screenheight()
root.title("SiKo for Dummies")
root.geometry(f"{w}x{h}+0+0")
root.config(background="white")

question = StringVar()
hint = StringVar()
state = StringVar()
answer = StringVar()
mitigation = StringVar()
risk = StringVar()
judgement = StringVar()
judgement_class = StringVar()


evaluation = []
current_index = -1
current = None


def reset():
    judgement.set("")
    judgement_class.set("")


def submit(*args):
    try:
        if judgement.get():
            evaluation.append(
                [
                    f'{int(current["ID"]):04d}',
                    current[columns["measure_id"]].split("_")[0],
                    "",
                    judgement_class.get() or judgement_choices[0],
                    judgement.get(),
                ]
            )
        reset()
        switch_to_next()
    except Exception:
        print_and_exit()


def print_and_exit(*args):
    writer = csv.writer(sys.stdout)
    writer.writerows(evaluation)
    with open(sys.argv[-1].split(".")[0] + "_result.csv", "w") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(evaluation)
    sys.exit()


def get_data():
    filename = sys.argv[-1]
    if filename.endswith(".csv"):
        return list(csv.DictReader(open(sys.argv[-1])))
    raise Exception("No support for this file type yet.")


def derive_language(data):
    if "State of Implementation" in d[0]:
        return "en"
    elif "Umsetzungsstatus" in d[0]:
        return "de"
    raise Exception("Cannot derive language")


data = get_data()
language = derive_language(data)
if language == "en":
    columns = {
        "id": "ID",
        "measure_id": "Measure ID",
        "description": "Description",
        "notice": "Notice",
        "state": "State of Implementation",
        "justification": "Justification",
        "mitigation": "Mitigating measure for deviation",
        "risk_id": "Risk ID",
    }
    states = [
        "Implementation dispendable",
        "Implemented",
        "Not completely implemented (risk)",
        "To be answered",
        "Not completely implemented (deviation)",
    ]
    judgement_choices = [
        "The statement of reasons is not conclusive or does not meet the requirements.",
        "The evaluation did not address all sub-items of the guideline.",
        "The mitigating measures are missing or incomplete.",
        "The mitigating measures do not eliminate the deviation.",
        "Status and reason don't match.",
        "The justification is not meaningful enough.",
        "The explanatory statement does not describe how the implementation takes place.",
        "Reason for deviation and mitigating measures are not cleanly separated.",
        "The explanatory memorandum does not cover all aspects of the requirement.",
        "The information on this specification is inconsistent with the information in other specifications.",
        "Reference to external document does not refer to the chapter heading.",
        "The results of the supplementary risk analysis were not taken  into account in the safety concept.",
        "The existing risk was not transferred to risk management.",
        "The alternative measures for the complete fulfilment of the protection goals are not comprehensibly documented.",
        "The alternative measures to fully meet the protection objectives do not eliminate the deviation.",
    ]
elif language == "de":
    columns = {
        "id": "ID",
        "measure_id": "Maßnahmen ID",
        "description": "Beschreibung",
        "notice": "Hinweis",
        "state": "Umsetzungsstatus",
        "justification": "Begründung",
        "mitigation": "Mitigierende Maßnahme für Abweichung",
        "risk_id": "Risikonummer",
    }
    states = [
        "Nicht relevant",
        "Vollständig umgesetzt",
        "Nicht vollständig umgesetzt (Risiko)",
        "Offen",
        "Nicht vollständig umgesetzt (Abweichung)",
    ]
    judgement_choices = [
        "Die Begründung ist inhaltlich nicht schlüssig oder trifft die Vorgabe nicht.",
        "Bei der Bewertung wurde nicht auf alle Unterpunkte der Vorgabe eingegangen.",
        "Die mitigierenden Maßnahmen fehlen oder sind unvollständig.",
        "Die mitigierenden Maßnahmen beseitigen nicht die Abweichung.",
        "Status und Begründung passen nicht zusammen.",
        "Die Begründung ist nicht aussagekräftig genug.",
        "Die Begründung beschreibt nicht, wie die Umsetzung erfolgt.",
        "Grund der Abweichung und mitigierende Maßnahmen sind nicht sauber getrennt.",
        "In der Begründung wird nicht auf alle Aspekte der Vorgabe eingegangen.",
        "Die Angaben zu dieser Vorgabe widersprechen den Angaben in anderen Vorgaben.",
        "Referenz auf externes Dokument verweist nicht auf die Kapitelüberschrift.",
        "Die Ergebnisse der ergänzenden Risikoanalyse wurde nicht angemessen im Sicherheitskonzept berücksichtigt.",
        "Das bestehende (Rest-)Risiko wurde nicht in das Risikomanagement überführt.",
        "Die alternative Maßnahmen zur vollständigen Erfüllung der Schutzziele sind nicht nachvollziehbar dokumentiert.",
        "Die alternative Maßnahmen zur vollständigen Erfüllung der Schutzziele beseitigen nicht die Abweichung.",
    ]


state_implemented = states[1]
state_risk = sttes[2]
state_deviation = states[4]


def switch_to_next():
    global current_index, current, has_risk
    current_index += 1
    if current_index >= len(data):
        raise Exception("Out of bounds")
    progressbar["value"] = current_index + 1
    current = data[current_index]
    question.set(current[columns["description"]])
    hint.set(current[columns["notice"]])
    state_value = current[columns["state"]]
    state.set(state_value)
    answer.set(current[columns["justification"]])
    if state_value == state_implemented:
        state_label.configure(background="green")
    elif state_value == state_deviation:
        state_label.configure(background="yellow")
    elif state_value in state_risk:
        state_label.configure(background="red")
    else:
        state_label.configure(background="gray")
    mitigation.set(current[columns["mitigation"]])
    risk.set(current[columns["risk_id"]])


frame = Frame(root, relief=GROOVE, width=50, height=100, bd=1)
frame.place(x=10, y=10)
canvas = Canvas(frame)
mainframe = Frame(canvas)
scrollbar = Scrollbar(frame, orient=VERTICAL, command=canvas.yview)
canvas.config(yscrollcommand=scrollbar.set)

default_font = font.nametofont("TkDefaultFont")
default_font.configure(size=18)

scrollbar.pack(side=RIGHT, fill=Y)
canvas.pack(side=LEFT)
canvas.config(background="white")
canvas.create_window((0, 0), window=mainframe, anchor="nw")
mainframe.bind(
    "<Configure>",
    lambda event: canvas.configure(
        scrollregion=canvas.bbox("all"), width=w - 30, height=h - 120
    ),
)
mainframe.config(background="white")

root.bind("<Return>", submit)
root.bind("<Shift-Return>", print_and_exit)
root.style = ttk.Style()
# ('clam', 'alt', 'default', 'classic')
root.style.theme_use("clam")
root.style.configure("TButton", font="helvetica 24")
root.style.configure(
    "Horizontal.TProgressbar", foreground="blue", background="#1da1f2", height=100
)
root.style.configure("TLabel", background="white")

judgement_class_widget = ttk.OptionMenu(mainframe, judgement_class, *judgement_choices)
judgement_class.set("")
judgement_class_widget.grid(row=0, column=2)
judgement_widget = ttk.Entry(mainframe, width=7, textvariable=judgement)
judgement_widget.grid(column=2, row=1, sticky=(W, E))

ttk.Button(mainframe, text="Next", command=submit).grid(column=8, row=1, sticky=W)

wrap = 1400
ttk.Label(mainframe, text="Requirement").grid(column=1, row=2, sticky=(N, E))
requirement_label = ttk.Label(mainframe, textvariable=question, wraplength=wrap)
requirement_label.grid(column=2, row=2, sticky=(W, E))
ttk.Label(mainframe, text="Hint").grid(column=1, row=3, sticky=(N, E))
ttk.Label(mainframe, textvariable=hint, wraplength=wrap).grid(
    column=2, row=3, sticky=(W, E)
)
ttk.Label(mainframe, text="State").grid(column=1, row=4, sticky=(N, E))
state_label = ttk.Label(mainframe, textvariable=state, wraplength=wrap)
state_label.grid(column=2, row=4, sticky=W)
ttk.Label(mainframe, text="Answer").grid(column=1, row=5, sticky=(N, E))
ttk.Label(mainframe, textvariable=answer, wraplength=wrap).grid(
    column=2, row=5, sticky=(W, E)
)
ttk.Label(mainframe, text="Mitigation").grid(column=1, row=6, sticky=(N, E))
ttk.Label(mainframe, textvariable=mitigation, wraplength=wrap).grid(
    column=2, row=6, sticky=(W, E)
)
ttk.Label(mainframe, text="Risk ID").grid(column=1, row=7, sticky=(N, E))
ttk.Label(mainframe, textvariable=risk, wraplength=wrap).grid(
    column=2, row=7, sticky=(W, E)
)
status = Frame(root)
progressbar = ttk.Progressbar(status, orient="horizontal", length=w, mode="determinate")
status.pack(side=BOTTOM, fill=X, expand=False)
progressbar.pack(side=BOTTOM, ipady=10)
progressbar["maximum"] = len(data)

for child in mainframe.winfo_children():
    child.grid_configure(padx=5, pady=5)

switch_to_next()
judgement_widget.focus()
root.mainloop()
