import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export default function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await register(email, username, password);
      if (r.needVerify) {
        toast.success("Check your email to verify your account.");
        nav("/login");
      } else {
        toast.success("Account created!");
        nav("/");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Register failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-12" data-testid="register-page">
      <h1 className="text-3xl font-bold font-heading mb-2">Create account</h1>
      <p className="text-zinc-500 mb-8">Join StreamHub free</p>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <Label>Email</Label>
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="bg-zinc-900 border-zinc-800" required data-testid="register-email" />
        </div>
        <div>
          <Label>Username</Label>
          <Input value={username} onChange={(e) => setUsername(e.target.value)} className="bg-zinc-900 border-zinc-800" required data-testid="register-username" />
        </div>
        <div>
          <Label>Password</Label>
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="bg-zinc-900 border-zinc-800" required data-testid="register-password" />
        </div>
        <Button type="submit" disabled={busy} className="w-full pro-gradient text-white border-0" data-testid="register-submit">
          {busy ? "Creating..." : "Sign Up"}
        </Button>
      </form>
      <p className="mt-6 text-zinc-500 text-sm">
        Have an account?{" "}
        <Link to="/login" className="text-rose-400 hover:text-rose-300">Sign in</Link>
      </p>
    </div>
  );
}
