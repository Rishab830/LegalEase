from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
import bcrypt

auth = Blueprint('auth', __name__)


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Validation
        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return redirect(url_for('auth.register'))

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return redirect(url_for('auth.register'))

        # Check if user already exists
        if User.find_by_email(email):
            flash('Email already registered.', 'error')
            return redirect(url_for('auth.register'))

        if User.find_by_username(username):
            flash('Username already taken.', 'error')
            return redirect(url_for('auth.register'))

        # Create user
        try:
            user_id = User.create_user(username, email, password)
            user = User.get(user_id)
            login_user(user)
            flash('Registration successful!', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            flash('An error occurred during registration.', 'error')
            return redirect(url_for('auth.register'))

    return render_template('register.html')


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('auth.login'))

        user_data = User.find_by_email(email)
        if not user_data:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))

        user = User(user_data)
        if not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))

        login_user(user)
        flash('Login successful!', 'success')
        next_page = request.args.get('next')
        return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))

    return render_template('login.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth.route('/profile', methods=['GET', 'PATCH'])
@login_required
def profile():
    """Display and update user profile."""
    if request.method == 'GET':
        # Display profile page
        return render_template('profile.html', user=current_user)
    
    # PATCH request - update profile
    if request.method == 'PATCH':
        data = request.get_json() or {}
        display_name = data.get('display_name')
        email = data.get('email')
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        # Validate required fields for password change
        if new_password and not current_password:
            return {'success': False, 'message': 'Current password required to change password.'}, 400

        # Verify current password if trying to update password
        if new_password:
            if not current_user.check_password(current_password):
                return {'success': False, 'message': 'Current password is incorrect.'}, 400
            
            if new_password != confirm_password:
                return {'success': False, 'message': 'New passwords do not match.'}, 400
            
            if len(new_password) < 6:
                return {'success': False, 'message': 'Password must be at least 6 characters long.'}, 400

        # Check if new email is already registered (if changing email)
        if email and email != current_user.email:
            existing_user = User.find_by_email(email)
            if existing_user:
                return {'success': False, 'message': 'Email already registered.'}, 400

        try:
            # Update profile fields
            if display_name or email:
                User.update_profile(current_user.id, display_name, email)

            # Update password if provided
            if new_password:
                User.update_password(current_user.id, new_password)

            # Refresh current user data
            user_data = User.get(current_user.id)
            if user_data:
                current_user.display_name = user_data.display_name
                current_user.email = user_data.email

            return {'success': True, 'message': 'Profile updated successfully!'}, 200

        except Exception as e:
            return {'success': False, 'message': 'An error occurred while updating profile.'}, 500