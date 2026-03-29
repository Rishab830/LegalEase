# Deploying LegalEase to the Cloud

You've made a great choice! **MongoDB Atlas** and **Render** are an excellent combination for a Flask application. Since you already have a `Dockerfile` set up with system dependencies (like Tesseract and Poppler), deploying via Render's Docker environment will be the smoothest path.

I've already gone ahead and **fixed the UTF-16LE encoding issue** in your `requirements.txt` file (which was causing those weird pip errors earlier) so that it will install seamlessly on a Linux machine like Render.

Here is your step-by-step guide to get everything online:

---

## 1. Set Up MongoDB Atlas (Database)

First, we need to move your local MongoDB data to the cloud.

1. Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) and register for a free account.
2. Build a **New Cluster** (the free M0 tier is perfectly fine).
3. Under **Database Access**, create a database user (e.g., `legalease_user`) and generate a secure password. **Save this password**.
4. Under **Network Access**, click "Add IP Address" and select **"Allow Access from Anywhere"** (`0.0.0.0/0`). This allows Render to connect to your database.
5. Go to your **Clusters** view, click **Connect**, select **Drivers**, select Python, and copy your connection string.
6. Swap out `<password>` in that connection string with your actual database user password. It will look something like this:
   `mongodb+srv://legalease_user:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`

---

## 2. Push Your Code to GitHub 

Render deploys directly from your GitHub repository.

1. Ensure your `.gitignore` correctly ignores the `venv/` folder, `.env`, and the `uploads/` folder so you don't commit large/sensitive files.
2. Commit your code if you haven't already:
   ```bash
   git add .
   git commit -m "Ready for Render deploy"
   git push origin main
   ```

---

## 3. Deploy to Render (Web Server)

Render will take your `Dockerfile`, build the image, and serve it.

1. Go to [Render](https://dashboard.render.com/) and create a free account if you haven't already.
2. Click **New +** and select **Web Service**.
3. Connect your GitHub account and select your `LegalEase` repository.
4. Render will automatically detect your `Dockerfile`. For the setup details:
   - **Name:** `legalease` (or whatever you prefer)
   - **Region:** Choose whatever is closest to your Atlas region
   - **Branch:** `main`
   - **Environment:** `Docker` (Render will detect this automatically from `Dockerfile`)
   - **Instance Type:** Free (or any paid tier if you choose)
5. Scroll down to **Environment Variables** and add the following keys so your app knows how to run:
   
   | Key | Value |
   | --- | --- |
   | `MONGO_URI` | *Paste your MongoDB Atlas connection string here!* |
   | `SECRET_KEY` | *Generate a random strong password here (e.g., `my-super-secret-key-123`)* |

6. Click **Create Web Service**.

> [!TIP]
> Render will take a few minutes to build your Docker image (it needs to install Python, Tesseract, Poppler, and your pip requirements). You can watch the progress in the Logs tab. 

---

## 4. What about the `uploads/` folder?
Because Render's free tier provides an **ephemeral disk**, files saved in `uploads/` might be wiped out every time Render restarts the server (which happens automatically upon a new deploy or periodically on the free tier). 

For now, this is okay for testing! However, if this goes straight to production, we would want to integrate something like **AWS S3** or **Cloudinary** for permanent document storage later down the line in Phase 2. Let me know if you reach that point and I can help set it up!
