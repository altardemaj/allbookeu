// AllBook — Main JS

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', function (e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth' });
    }
  });
});

// Navbar scroll effect
const navbar = document.querySelector('.navbar');
if (navbar) {
  window.addEventListener('scroll', () => {
    if (window.scrollY > 20) {
      navbar.style.boxShadow = '0 4px 32px rgba(0,0,0,0.6)';
    } else {
      navbar.style.boxShadow = 'none';
    }
  });
}

// Lazy-load images with fade-in
if ('IntersectionObserver' in window) {
  const imgs = document.querySelectorAll('img[loading="lazy"]');
  imgs.forEach(img => {
    img.style.opacity = '0';
    img.style.transition = 'opacity 0.4s ease';
    img.addEventListener('load', () => { img.style.opacity = '1'; });
    if (img.complete) img.style.opacity = '1';
  });
}

// Hero search: focus effect
const heroInput = document.querySelector('.hero-search-field input');
if (heroInput) {
  const box = document.querySelector('.hero-search-box');
  heroInput.addEventListener('focus', () => {
    box.style.boxShadow = '0 12px 48px rgba(108,71,255,0.35)';
  });
  heroInput.addEventListener('blur', () => {
    box.style.boxShadow = '0 8px 40px rgba(0,0,0,0.25)';
  });
}

// Counter animation for stats
function animateCounters() {
  document.querySelectorAll('.stat-num').forEach(el => {
    const text = el.textContent;
    const num = parseFloat(text.replace(/[^0-9.]/g, ''));
    if (!num) return;
    const suffix = text.replace(/[0-9.,]/g, '');
    let start = 0;
    const step = num / 60;
    const timer = setInterval(() => {
      start += step;
      if (start >= num) {
        el.textContent = text;
        clearInterval(timer);
      } else {
        const display = num >= 1000
          ? (start / 1000).toFixed(0) + 'K'
          : start.toFixed(num < 10 ? 1 : 0);
        el.textContent = display + suffix;
      }
    }, 16);
  });
}

// Trigger counter animation when stats section is visible
const statsSection = document.querySelector('.stats-section');
if (statsSection) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateCounters();
        observer.disconnect();
      }
    });
  }, { threshold: 0.4 });
  observer.observe(statsSection);
}
