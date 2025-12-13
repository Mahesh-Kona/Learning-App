"""Add random mobile numbers to all students"""
import pymysql
import random

# Generate random 10-digit mobile number
def generate_mobile():
    # Indian mobile numbers start with 6-9 for first digit
    first_digit = random.choice(['6', '7', '8', '9'])
    remaining_digits = ''.join([str(random.randint(0, 9)) for _ in range(9)])
    return first_digit + remaining_digits

# Connect to MariaDB
conn = pymysql.connect(
    host='localhost',
    user='root',
    password='',
    database='learning',
    charset='utf8mb4'
)

try:
    with conn.cursor() as cursor:
        # Get all students
        cursor.execute("SELECT id, name, mobile FROM students")
        students = cursor.fetchall()
        
        print(f"Found {len(students)} students\n")
        print("=" * 60)
        
        updated_count = 0
        
        for student_id, name, current_mobile in students:
            if not current_mobile:
                new_mobile = generate_mobile()
                cursor.execute("UPDATE students SET mobile = %s WHERE id = %s", (new_mobile, student_id))
                print(f"✓ Student ID {student_id} ({name}): {new_mobile}")
                updated_count += 1
            else:
                print(f"- Student ID {student_id} ({name}): {current_mobile} (already set)")
        
        conn.commit()
        
        print("=" * 60)
        print(f"\n✓ Updated {updated_count} students with random mobile numbers")
        
        # Verify
        print("\nVerification:")
        cursor.execute("SELECT id, name, mobile FROM students")
        students = cursor.fetchall()
        for student_id, name, mobile in students:
            print(f"  ID {student_id}: {name} - {mobile}")
        
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    conn.close()
