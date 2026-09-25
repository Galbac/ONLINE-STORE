import os

BASE_DIR = '/Users/zidansaparbegov/PycharmProjects/GroceryStore-front'
view_path = os.path.join(BASE_DIR, 'src/widgets/admin-dashboard/ui/AdminDashboardView.tsx')

# Read current file to preserve secondary widgets untouched
with open(view_path, 'r', encoding='utf-8') as f:
    orig = f.read()

# Let's inspect where secondary widgets start (after DeliverySplitWidget, around line 510)
# We can cleanly replace the top part and the widgets specified by the user!
print("Original length:", len(orig))
