import SpendingExplorer from "@/components/SpendingExplorer";

export const metadata = {
  title: "Where the money goes | CivicLens",
  description:
    "Cook County township and county spending, ranked and broken down by category from Annual Financial Reports.",
};

export default function SpendingPage() {
  return <SpendingExplorer />;
}
