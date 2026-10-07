// Template profile: a fictional person, to copy into profiles/<your-id>/ and rewrite.
// Build it with ./build.sh <your-id>; preview it live with index.html?profile=<your-id>&v=main.
// Every text below is checked by atscheck.py: the headline, each tagline item and each skill term
// must come out intact in the PDF text, so write them the way job ads write them.

window.PROFILE = {
  theme: "classic",            // a file in themes/, without .css
  fileStem: "CV-Alex-Martin",  // PDF name: out/<id>/<fileStem>-<variant>.pdf
  lang: "en",                  // <html lang>, stored as the PDF language
  photo: null,                 // "photo.png" next to this file, or null for an initials circle
  // One entry per variant; add more (e.g. backend, sre) to target different roles from one file.
  variants: {
    main: {
      // label: "Backend",          // optional: the name the application tracker shows; default: the headline
      name: "ALEX MARTIN",
      headline: "Backend Engineer",
      tagline: ["Python", "APIs", "PostgreSQL", "Cloud"],
      profile: "Backend engineer who builds and runs Python services: REST APIs, data pipelines and the CI that ships them. I like small, well-tested changes and clear on-call runbooks. Open to backend and platform roles in Lyon or remote.",
      // [label, value]: the value is split on commas, and on commas inside brackets, into must-have terms.
      // The first term of each line goes to the PDF Keywords, except on the "Languages" line (spoken languages).
      skills: [
        ["Code", "Python, Go, SQL, Bash"],
        ["Frameworks", "FastAPI, Django, Celery"],
        ["Data", "PostgreSQL, Redis, Kafka"],
        ["Cloud", "AWS (ECS, RDS, S3), Terraform"],
        ["Delivery", "Docker, GitHub Actions, code review"],
        ["Quality", "pytest, contract testing, observability"],
        ["Languages", "English, French"]
      ],
      // A job has either items (bullets) or text (one line).
      experience: [
        { dates: "Jan 2023 \u2013 present", title: "Backend Engineer", org: "Example Logistics, Lyon", items: [
          "Split a monolith into four FastAPI services; deploys went from weekly to daily.",
          "Cut the p95 latency of the tracking API from 800 ms to 150 ms with query and cache work.",
          "Moved the infrastructure to Terraform on AWS, reviewed by the whole team.",
          "Wrote the on-call runbooks and led the post-mortems for the service."
        ] },
        { dates: "Sep 2020 \u2013 Dec 2022", title: "Software Engineer", org: "Sample Retail", items: [
          "Built the order export pipeline on Celery and PostgreSQL.",
          "Added contract tests between the shop and the payment service."
        ] },
        { dates: "2019 \u2013 2020", title: "Junior Developer", org: "Demo Agency",
          text: "Django sites and REST APIs for small business clients." }
      ],
      education: [
        { title: "MSc Computer Science", org: "Example University", dates: "2017 \u2013 2019" }
      ],
      contact: {
        email: "alex.martin@example.com",
        city: "Lyon",
        // linkedin: { label: "linkedin.com/in/<you>", url: "https://www.linkedin.com/in/<you>/" },
        site: { label: "alex-martin.example.com", url: "https://alex-martin.example.com/" }
      }
    }
  }
};
