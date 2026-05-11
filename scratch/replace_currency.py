import os

files_to_update = [
    r'finance\models.py',
    r'finance\views.py',
    r'procurement\models.py',
    r'templates\dashboard\admin_dashboard.html',
    r'templates\dashboard\invoice_print.html',
    r'templates\dashboard\manage_finance.html',
    r'templates\dashboard\parent_dashboard.html',
    r'templates\dashboard\student_dashboard.html',
    r'templates\dashboard\student_profile_detail.html',
    r'templates\procurement\account_statement.html',
    r'templates\procurement\inventory_capex.html',
    r'templates\procurement\manage_expenses.html',
    r'templates\procurement\purchase_requests.html',
]

for file_path in files_to_update:
    abs_path = os.path.join(os.getcwd(), file_path)
    if os.path.exists(abs_path):
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = content.replace('Rs.', 'Tk.').replace('Rs ', 'Tk ')
        
        if content != new_content:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated: {file_path}")
        else:
            print(f"No changes needed: {file_path}")
    else:
        print(f"File not found: {file_path}")
