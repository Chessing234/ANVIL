import { CredentialWallet } from "@/components/student/CredentialWallet";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

export function Credentials() {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold text-indigo-50">Credential wallet</h1>
          <p className="mt-1 max-w-2xl text-indigo-200/85">
            NFT-style attestations with filters, blockchain verify panel, and shareable proof links for verifiable skill credentials.
          </p>
        </div>
        <Button asChild variant="outline" className="border-indigo-700 text-indigo-50">
          <Link to="/profile">Back to profile</Link>
        </Button>
      </div>
      <CredentialWallet />
    </div>
  );
}
