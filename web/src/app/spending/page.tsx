import SpendingExplorer from "@/components/SpendingExplorer";

export const metadata = {
  title: "Where the money goes | CivicLens",
  description:
    "Cook County township, municipal, and county spending by layer for FY2023–FY2025, from Illinois Comptroller Annual Financial Reports.",
};

export default function SpendingPage() {
  return <SpendingExplorer />;
}
