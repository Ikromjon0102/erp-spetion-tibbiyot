from django.contrib import admin

from .models import Expense, ExpenseCategory, Payslip, RecurringExpense, SalaryPayment, SalaryRule

admin.site.register(ExpenseCategory)
admin.site.register(Expense)
admin.site.register(RecurringExpense)
admin.site.register(SalaryRule)
admin.site.register(Payslip)
admin.site.register(SalaryPayment)
