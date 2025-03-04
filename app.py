from flask import Flask, request, send_file, render_template
import pandas as pd
import io
from ortools.linear_solver import pywraplp

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def truckLoader():
    if request.method == 'POST':
        file = request.files.get('file')
        if file:
            truckwise_shipments, shipmentwise_trucks = solve(file)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                shipmentwise_trucks.to_excel(writer, index=False, sheet_name='shipmentwise_trucks')
                truckwise_shipments.to_excel(writer, index=False, sheet_name='truckwise_shipments')
            output.seek(0)
            return send_file(
                output,
                as_attachment=True,
                download_name='Optimal_Loading_Plan.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        return "No file uploaded!", 400

    return render_template('Truckloader.html')

def create_truckloader_data(file):
    shipments = pd.read_excel(file, sheet_name=0)
    trucks = pd.read_excel(file, sheet_name=1)

    data = {
        "shipments": shipments,
        "trucks": trucks,
        "shipmentsNumber": list(range(shipments.shape[0])),
        "trucktypesNumber": list(range(trucks.shape[0]))
    }
    return data

def solve(file):
    df = create_truckloader_data(file)
    solver = pywraplp.Solver.CreateSolver("SCIP")

    if not solver:
        return None, None

    x = {}
    for i in df["shipmentsNumber"]:
        for j in df["trucktypesNumber"]:
            for k in range(df["trucks"].loc[j, "Number of Trucks"]):
                if (df["shipments"].loc[i, "Origin"] == df["trucks"].loc[j, "Origin"] and 
                    df["shipments"].loc[i, "Destination"] == df["trucks"].loc[j, "Destination"]):
                    x[(i, j, k)] = solver.IntVar(0, 1, f"x_{i}_{j}_{k}")
                else:
                    x[(i, j, k)] = solver.IntVar(0, 0, f"x_{i}_{j}_{k}")
                      
    y = {}
    for j in df["trucktypesNumber"]:
        for k in range(df["trucks"].loc[j, "Number of Trucks"]):
            y[(j, k)] = solver.IntVar(0, 1, f"y_{j}_{k}")

    for i in df["shipmentsNumber"]:
        solver.Add(sum(x[i, j, k] for j in df["trucktypesNumber"] for k in range(df["trucks"].loc[j, "Number of Trucks"])) == 1)

    for j in df["trucktypesNumber"]:
        for k in range(df["trucks"].loc[j, "Number of Trucks"]):
            solver.Add(
                sum(x[(i, j, k)] * df["shipments"].loc[i, "Weight"] for i in df["shipmentsNumber"]) 
                <= y[(j, k)] * df["trucks"].loc[j, "Truck Capacity (Kg Weight)"]
            )

    solver.Minimize(solver.Sum(y[j, k] for j in df["trucktypesNumber"] for k in range(df["trucks"].loc[j, "Number of Trucks"])))
    
    status = solver.Solve()
    output = pd.DataFrame(columns=['Truck', 'Origin', 'Destination', 'Shipments'])
    df["shipments"]["Truck"] = ""

    if status == pywraplp.Solver.OPTIMAL:
        for j in df["trucktypesNumber"]:
            for k in range(df["trucks"].loc[j, "Number of Trucks"]):
                if y[j, k].solution_value() == 1:
                    truck_shipments = [i+1 for i in df["shipmentsNumber"] if x[i, j, k].solution_value() > 0]
                    df["shipments"].loc[df["shipmentsNumber"], 'Truck'] = f"{j+1}_{k+1}"
                    if truck_shipments:
                        output = pd.concat([output, pd.DataFrame({
                            'Truck': f"{j+1}_{k+1}",
                            'Origin': df["trucks"].loc[j, "Origin"],
                            'Destination': df["trucks"].loc[j, "Destination"],
                            'Shipments': [truck_shipments]
                        })], ignore_index=True)
    return output, df["shipments"]

if __name__ == '__main__':
    app.run(debug=True)
