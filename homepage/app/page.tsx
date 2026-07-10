import { BenefitCards } from "@/components/BenefitCards";
import { CTA } from "@/components/CTA";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { Hero } from "@/components/Hero";
import { ProductScreenshot } from "@/components/ProductScreenshot";
import { ProofFooter } from "@/components/ProofFooter";
import { ReassuranceStrip } from "@/components/ReassuranceStrip";
import { SearchFlowProvider } from "@/components/SearchFlowContext";
import { SearchResults } from "@/components/SearchResults";

export default function HomePage() {
  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-site px-4 pb-8 pt-5 sm:px-5">
        <Header />
        <SearchFlowProvider>
          <main>
            <Hero />
            <SearchResults />
            <BenefitCards />
            <ProductScreenshot />
            <ReassuranceStrip />
            <ProofFooter />
            <CTA />
          </main>
        </SearchFlowProvider>
        <Footer />
      </div>
    </div>
  );
}
