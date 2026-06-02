import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { Toaster } from "sonner";
import { Layout } from "@/layout/Layout";
import Home from "@/pages/Home";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Upload from "@/pages/Upload";
import Watch from "@/pages/Watch";
import Profile from "@/pages/Profile";
import Pro from "@/pages/Pro";
import Admin from "@/pages/Admin";
import Category from "@/pages/Category";
import Contact from "@/pages/Contact";
import EditVideo from "@/pages/EditVideo";
import VideoList from "@/pages/VideoList";
import SiteHead from "@/components/SiteHead";

function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <BrowserRouter>
          <SiteHead />
          <Toaster theme="dark" position="bottom-right" richColors />
          <Routes>
            {/* Watch page uses its own Layout (with recommendations) */}
            <Route path="/watch/:id" element={<Watch />} />
            {/* All other pages use shared Layout */}
            <Route element={<Layout />}>
              <Route index element={<Home />} />
              <Route path="/popular" element={<VideoList variant="popular" />} />
              <Route path="/discover" element={<VideoList variant="discover" />} />
              <Route path="/shorts" element={<VideoList variant="shorts" />} />
              <Route path="/all-episodes" element={<VideoList variant="all" />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/upload" element={<Upload />} />
              <Route path="/profile/:id" element={<Profile />} />
              <Route path="/pro" element={<Pro />} />
              <Route path="/pro/success" element={<Pro />} />
              <Route path="/category/:id" element={<Category />} />
              <Route path="/contact" element={<Contact />} />
              <Route path="/edit-video/:id" element={<EditVideo />} />
              <Route path="/admin" element={<Admin />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </LanguageProvider>
  );
}

export default App;
